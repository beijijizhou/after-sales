from datetime import datetime, time
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from automation.playwright.chrome_session import connect_debug_chrome
from automation.playwright.errors import ProductionLoginRequired
from automation.playwright.haloo.platforms import get_erp_platform


API_FRAME_NAME = "fnsz-sale"
MODULE_PREFIX = "productItemManage-"
LIST_API_PATH = "/production/v1/production/order/item/page"
NY_TIMEZONE = ZoneInfo("America/New_York")
PAGE_SIZE = 5000
REQUEST_ATTEMPTS = 3
SNAPSHOT_ATTEMPTS = 2


def build_production_item_payload(
    start_date,
    end_date,
    page=1,
    page_size=PAGE_SIZE,
):
    start_at = datetime.combine(start_date, time.min, NY_TIMEZONE)
    end_at = datetime.combine(end_date, time.max, NY_TIMEZONE)
    return {
        "page": page,
        "page_size": page_size,
        "sum_total_qty": True,
        "status": [],
        "order_compositions": [],
        "process_route_ids": [],
        "order_third_status_list": [],
        "performance_status_list": [],
        "system_performance_status_list": [],
        "shipping_status_list": [],
        "order_source_list": [],
        "logistics_sorting_code_list": [],
        "begin_production_time": {
            "from": str(int(start_at.timestamp() * 1000)),
            "to": str(int(end_at.timestamp() * 1000)),
        },
        "styles": {"style_sku_ids": []},
        "sort": [{"sort_by": "created", "sort_type": 2}],
    }


def fetch_humbird_production_records(
    platform,
    start_date,
    end_date,
    report_progress=None,
):
    erp = get_erp_platform(platform)
    report = report_progress or (lambda _message: None)
    report(f"正在连接已登录的 {platform} ERP 会话")

    with sync_playwright() as playwright:
        browser = connect_debug_chrome(
            playwright, erp.production_items_url
        )
        page = _authenticated_production_page(browser, erp)
        report(f"{platform} 登录状态有效，正在识别页面生产数据接口")
        module_url = _discover_production_module(page)
        report(f"{platform} 已识别页面真实接口，正在读取生产数据")

        last_error = None
        for snapshot_attempt in range(1, SNAPSHOT_ATTEMPTS + 1):
            try:
                rows, total = _collect_snapshot(
                    page,
                    start_date,
                    end_date,
                    platform,
                    report,
                    module_url,
                )
                if len(rows) == total:
                    return rows
                last_error = RuntimeError(
                    f"{platform} 接口返回 {len(rows):,} 条，但总数为 "
                    f"{total:,}"
                )
            except Exception as error:
                last_error = error

            if snapshot_attempt < SNAPSHOT_ATTEMPTS:
                report(
                    f"{platform} 第一次读取未通过完整性校验："
                    f"{last_error}；正在重新核对"
                )

    raise RuntimeError(
        f"{platform} 数据完整性校验失败：{last_error}；"
        "已停止使用不完整数据"
    )


def _collect_snapshot(
    page,
    start_date,
    end_date,
    platform,
    report,
    module_url,
):
    first = _list_with_retry(
        page,
        build_production_item_payload(start_date, end_date),
        module_url,
        platform,
        1,
    )
    total = int(first.get("total") or 0)
    rows = list(first.get("list") or [])
    report(f"{platform} 共 {total:,} 条，正在读取分页数据")

    page_number = 1
    while len(rows) < total:
        page_number += 1
        result = _list_with_retry(
            page,
            build_production_item_payload(
                start_date, end_date, page=page_number
            ),
            module_url,
            platform,
            page_number,
        )
        page_rows = list(result.get("list") or [])
        if not page_rows:
            break
        rows.extend(page_rows)
        rows = _deduplicate_rows(rows)
        report(f"{platform} 已读取 {len(rows):,} / {total:,} 条")
    return rows, total


def _list_with_retry(page, payload, module_url, platform, page_number):
    last_error = None
    for attempt in range(1, REQUEST_ATTEMPTS + 1):
        try:
            return _list_production_items(page, payload, module_url)
        except Exception as error:
            last_error = error
            if attempt < REQUEST_ATTEMPTS:
                page.wait_for_timeout(400 * attempt)
    raise RuntimeError(
        f"第 {page_number} 页连续 {REQUEST_ATTEMPTS} 次读取失败："
        f"{last_error}"
    )


def _authenticated_production_page(browser, erp):
    pages = [
        page
        for context in browser.contexts
        for page in context.pages
        if erp.host in page.url
        and "/produceManage/produceItemsManage" in page.url
        and "/login" not in page.url
    ]
    page = pages[-1] if pages else _open_production_page(browser, erp)
    for _ in range(60):
        if "/login" in page.url:
            raise ProductionLoginRequired(
                f"请在已打开的专用 Chrome 中完成 {erp.name} 登录后重试"
            )
        if _api_frame(page) is not None:
            return page
        page.wait_for_timeout(500)
    raise RuntimeError(f"{erp.name} 生产模块加载超过 30 秒")


def _open_production_page(browser, erp):
    if not browser.contexts:
        raise RuntimeError("专用 Chrome 没有可用的浏览器窗口")
    page = browser.contexts[0].new_page()
    page.goto(
        erp.production_items_url,
        wait_until="domcontentloaded",
        timeout=30_000,
    )
    if "/login" in page.url:
        raise ProductionLoginRequired(
            f"已为你打开 {erp.name} 登录页；完成登录后请重新读取"
        )
    return page


def _discover_production_module(page):
    for attempt in range(2):
        frame = _api_frame(page)
        if frame is not None:
            module_url = _module_url(frame)
            if module_url and _module_has_list_api(frame, module_url):
                return module_url
        if attempt == 0:
            page.reload(wait_until="domcontentloaded", timeout=30_000)
            for _ in range(60):
                if _api_frame(page) is not None:
                    break
                page.wait_for_timeout(500)
    raise RuntimeError("未找到蜂鸟当前版本的生产列表接口模块")


def _module_has_list_api(frame, module_url):
    return frame.evaluate(
        """async ({url, path}) => {
            const api = await import(url);
            return Object.values(api).some(
                value => typeof value === "function"
                    && String(value).includes(path)
            );
        }""",
        {"url": module_url, "path": LIST_API_PATH},
    )


def _list_production_items(page, payload, module_url):
    frame = _api_frame(page)
    if frame is None:
        raise RuntimeError("生产模块 iframe 不存在或仍在加载")
    response = frame.evaluate(
        """async ({url, path, payload}) => {
            const api = await import(url);
            const entry = Object.entries(api).find(
                ([, value]) => typeof value === "function"
                    && String(value).includes(path)
            );
            if (!entry) {
                throw new Error("ERP production list API export not found");
            }
            return await entry[1](payload);
        }""",
        {
            "url": module_url,
            "path": LIST_API_PATH,
            "payload": payload,
        },
    )
    return _normalize_api_result(response)


def _normalize_api_result(response):
    current = response
    for _ in range(5):
        if not isinstance(current, dict):
            break
        if "list" in current and "total" in current:
            return current
        nested = next(
            (
                current.get(key)
                for key in ("data", "result", "body")
                if isinstance(current.get(key), dict)
            ),
            None,
        )
        if nested is None:
            break
        current = nested
    raise RuntimeError("生产接口响应中没有 list / total")


def _deduplicate_rows(rows):
    result = []
    seen_codes = set()
    for row in rows:
        code = row.get("code") if isinstance(row, dict) else None
        if code not in (None, ""):
            marker = str(code)
            if marker in seen_codes:
                continue
            seen_codes.add(marker)
        result.append(row)
    return result


def _api_frame(page):
    return next(
        (frame for frame in page.frames if frame.name == API_FRAME_NAME),
        None,
    )


def _module_url(frame):
    resources = frame.evaluate(
        "() => performance.getEntriesByType('resource').map(x => x.name)"
    )
    matches = [
        url
        for url in resources
        if "/static/js/chunk/" in url
        and url.rsplit("/", 1)[-1].startswith(MODULE_PREFIX)
    ]
    return matches[-1] if matches else None
