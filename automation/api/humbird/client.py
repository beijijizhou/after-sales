from datetime import datetime, time
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from automation.playwright.chrome_session import connect_debug_chrome
from automation.playwright.errors import ProductionLoginRequired
from automation.playwright.haloo.platforms import get_erp_platform


API_FRAME_NAME = "fnsz-sale"
MODULE_PREFIX = "productItemManage-"
MODULE_FALLBACK = "productItemManage-BvTyos5U.js"
CHUNK_ROOT = "https://fe-product.hihumbird.com/static/js/chunk/"
NY_TIMEZONE = ZoneInfo("America/New_York")
PAGE_SIZE = 5000


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
        report(f"{platform} 登录状态有效，正在通过 API 读取生产数据")
        first = _list_production_items(
            page,
            build_production_item_payload(start_date, end_date),
        )
        total = int(first.get("total") or 0)
        rows = list(first.get("list") or [])
        report(f"{platform} 共 {total:,} 条，正在读取分页数据")

        page_number = 1
        while len(rows) < total:
            page_number += 1
            result = _list_production_items(
                page,
                build_production_item_payload(
                    start_date, end_date, page=page_number
                ),
            )
            page_rows = list(result.get("list") or [])
            if not page_rows:
                break
            rows.extend(page_rows)
            report(f"{platform} 已读取 {len(rows):,} / {total:,} 条")

    if len(rows) != total:
        raise RuntimeError(
            f"{platform} API 返回 {len(rows):,} 条，但总数为 "
            f"{total:,}，已停止使用不完整数据"
        )
    return rows


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
        if _api_frame(page) is not None:
            return page
        page.wait_for_timeout(500)
    raise RuntimeError(f"{erp.name} 生产模块加载超过 30 秒")


def _open_production_page(browser, erp):
    host_pages = [
        page
        for context in browser.contexts
        for page in context.pages
        if erp.host in page.url
    ]
    if not host_pages:
        raise ProductionLoginRequired(
            f"请先在专用 Chrome 中打开并登录 {erp.name}"
        )
    page = host_pages[-1].context.new_page()
    page.goto(
        erp.production_items_url,
        wait_until="domcontentloaded",
        timeout=30_000,
    )
    if "/login" in page.url:
        raise ProductionLoginRequired(
            f"请先在专用 Chrome 中完成 {erp.name} 登录"
        )
    return page


def _list_production_items(page, payload):
    frame = _api_frame(page)
    module_url = _module_url(frame)
    return frame.evaluate(
        """async ({url, payload}) => {
            const api = await import(url);
            if (typeof api.a !== "function") {
                throw new Error("ERP production API export not found");
            }
            return await api.a(payload);
        }""",
        {"url": module_url, "payload": payload},
    )


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
    return matches[-1] if matches else CHUNK_ROOT + MODULE_FALLBACK
