import re

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


EXPORT_RECORD_PATH = "/factory/exportRecord"
MAX_GENERATION_WAIT_SECONDS = 8 * 60
REFRESH_INTERVAL_SECONDS = 15


def find_export_record_page(browser):
    return next(
        (
            page
            for context in browser.contexts
            for page in context.pages
            if EXPORT_RECORD_PATH in page.url
        ),
        None,
    )


def find_ready_undownloaded_row(page):
    if page is None:
        return None
    row = _latest_bill_row(page)
    if row is None:
        return None
    text = _normalize(row.inner_text())
    if "已生成" in text and "下载(未下载)" in text:
        return row
    return None


def download_row(page, row):
    return _download_row(page, row)


def submit_and_download(page, report):
    previous_pages = set(page.context.pages)
    _click_text(page, "条件导出")
    _confirm_export(page)
    report("S2B 导出任务已提交，正在打开导出记录")
    records_page = _wait_for_records_page(page, previous_pages)
    row = _wait_until_generated(records_page, report)
    report("S2B Excel 已生成，正在下载")
    return _download_row(records_page, row)


def _confirm_export(page):
    for _ in range(40):
        modals = page.locator(".ant-modal")
        for index in range(modals.count()):
            modal = modals.nth(index)
            if not modal.is_visible():
                continue
            buttons = modal.locator("button")
            for button_index in range(buttons.count()):
                button = buttons.nth(button_index)
                if (
                    button.is_visible()
                    and button.is_enabled()
                    and _normalize(button.inner_text()) == "确定"
                ):
                    button.click()
                    return
        page.wait_for_timeout(250)
    raise RuntimeError("S2B 条件导出弹窗未出现")


def _wait_for_records_page(source_page, previous_pages):
    for _ in range(80):
        new_pages = [
            page
            for page in source_page.context.pages
            if page not in previous_pages
            and "overseasfactory.s2bdiy.com" in page.url
        ]
        if new_pages:
            page = new_pages[-1]
            page.wait_for_load_state("domcontentloaded")
            return page
        if "/factory/billDetails" not in source_page.url:
            return source_page
        source_page.wait_for_timeout(250)
    raise RuntimeError("S2B 导出后没有进入导出记录页")


def _wait_until_generated(page, report):
    _wait_for_table(page)
    elapsed = 0
    delay = 3
    next_progress = 60
    report("S2B Excel 正在生成，将按低频刷新等待完成")
    while elapsed <= MAX_GENERATION_WAIT_SECONDS:
        row = _latest_bill_row(page)
        if row is not None:
            if _has_download(row):
                return row
            if "生成失败" in _normalize(row.inner_text()):
                raise RuntimeError("S2B Excel 生成失败")
        if elapsed >= MAX_GENERATION_WAIT_SECONDS:
            break
        page.wait_for_timeout(delay * 1_000)
        elapsed += delay
        try:
            page.reload(wait_until="domcontentloaded", timeout=30_000)
        except PlaywrightTimeoutError:
            pass
        _wait_for_table(page)
        if elapsed >= next_progress:
            report(f"S2B Excel 仍在生成，已等待 {elapsed} 秒")
            next_progress += 60
        delay = REFRESH_INTERVAL_SECONDS
    raise RuntimeError("S2B Excel 生成超过8分钟，请稍后查看导出记录")


def _wait_for_table(page):
    page.locator("tbody tr").first.wait_for(state="visible", timeout=15_000)


def _latest_bill_row(page):
    rows = page.locator("tbody tr")
    for index in range(rows.count()):
        row = rows.nth(index)
        text = row.inner_text()
        if (
            row.is_visible()
            and "财务中心页面" in text
            and "工厂导出应收货款账单" in text
        ):
            return row
    return None


def _has_download(row):
    links = row.get_by_text(re.compile(r"下载"))
    return any(
        links.nth(index).is_visible()
        for index in range(links.count())
    )


def _download_row(page, row):
    links = row.get_by_text(re.compile(r"下载"))
    for index in range(links.count()):
        link = links.nth(index)
        if not link.is_visible():
            continue
        try:
            with page.expect_download(timeout=120_000) as download_info:
                link.click()
            return download_info.value
        except PlaywrightTimeoutError as error:
            raise RuntimeError("S2B 已点击下载，但未收到 Excel") from error
    raise RuntimeError("S2B 记录已生成，但没有找到下载按钮")


def _click_text(page, text):
    matches = page.get_by_text(text, exact=True)
    for index in range(matches.count()):
        candidate = matches.nth(index)
        if candidate.is_visible():
            candidate.click()
            return
    raise RuntimeError(f"S2B 没有找到按钮：{text}")


def _normalize(value):
    return re.sub(r"\s+", "", str(value or ""))
