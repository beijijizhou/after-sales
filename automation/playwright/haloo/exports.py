import re

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from automation.playwright.haloo.filters import click_named_button


EXPORT_RECORDS_PATH = "/productionData/exportRecords/"


def find_export_records_page(browser, host=None):
    pages = [page for context in browser.contexts for page in context.pages]
    return next(
        (
            page
            for page in pages
            if EXPORT_RECORDS_PATH in page.url
            and (host is None or host in page.url)
        ),
        None,
    )


def find_matching_export_row(
    page, start_date, end_date, require_success=False
):
    start_text = f"{start_date:%Y-%m-%d} 00:00:00"
    end_text = f"{end_date:%Y-%m-%d} 23:59:59"
    expected = [
        "生产项",
        "导出生产项",
        "生产时间",
        start_text,
        end_text,
    ]
    for frame in page.frames:
        rows = frame.locator("tbody tr")
        for index in range(rows.count()):
            row = rows.nth(index)
            text = row.inner_text()
            if not all(value in text for value in expected):
                continue
            if require_success and "生成成功" not in text:
                continue
            return row
    return None


def download_export_row(page, row):
    links = row.get_by_text("下载", exact=True)
    for index in range(links.count()):
        link = links.nth(index)
        if not link.is_visible():
            continue
        try:
            with page.expect_download(timeout=120_000) as download_info:
                link.click()
            return download_info.value
        except PlaywrightTimeoutError as error:
            raise RuntimeError("已点击导出记录的下载，但未收到 Excel") from error
    raise RuntimeError("导出记录已生成，但没有找到下载按钮")


def submit_and_download(page, start_date, end_date, report):
    previous_pages = set(page.context.pages)
    click_named_button(page, ["导出生产项"])
    _click_export_confirmation(page)
    report("导出任务已提交，正在等待生成文件")
    records_page = _wait_for_records_page(page, previous_pages)
    row = _wait_for_export_row(records_page, start_date, end_date, report)
    report("导出文件已生成，正在点击下载")
    return download_export_row(records_page, row)


def close_stale_export_modal(page):
    modal = _find_export_modal(page)
    if modal is None:
        return
    close_button = modal.locator("button.ant-modal-close")
    if close_button.count() and close_button.first.is_visible():
        close_button.first.click(force=True)
        page.wait_for_timeout(300)


def _wait_for_records_page(source_page, previous_pages):
    source_host = source_page.url.split("/", 3)[2]
    for _ in range(80):
        candidates = [
            page
            for page in source_page.context.pages
            if EXPORT_RECORDS_PATH in page.url
            and source_host in page.url
            and (page not in previous_pages or page is source_page)
        ]
        if candidates:
            page = candidates[-1]
            page.wait_for_load_state("domcontentloaded")
            return page
        source_page.wait_for_timeout(250)
    raise RuntimeError("导出任务已提交，但没有进入导出记录页")


def _wait_for_export_row(page, start_date, end_date, report):
    for attempt in range(240):
        row = find_matching_export_row(page, start_date, end_date)
        if row is not None:
            text = _normalize_text(row.inner_text())
            if "生成成功" in text and "下载" in text:
                return row
            if "生成失败" in text:
                raise RuntimeError("生产项导出任务生成失败")
        if attempt and attempt % 10 == 0:
            report(f"文件仍在生成中，已等待 {attempt} 秒")
        page.wait_for_timeout(1000)
    raise RuntimeError("导出任务已提交，但四分钟内未生成完成")


def _click_export_confirmation(page):
    for _ in range(40):
        modal = _find_export_modal(page)
        if modal is not None:
            buttons = modal.locator("button")
            for index in range(buttons.count()):
                button = buttons.nth(index)
                if (
                    button.is_visible()
                    and button.is_enabled()
                    and _normalize_text(button.inner_text()) == "导出"
                ):
                    button.click()
                    return
        page.wait_for_timeout(250)
    raise RuntimeError("已点击导出生产项，但确认弹窗未出现")


def _find_export_modal(page):
    for frame in page.frames:
        modals = frame.locator(".ant-modal")
        for index in range(modals.count()):
            modal = modals.nth(index)
            if modal.is_visible() and "导出生产项" in modal.inner_text():
                return modal
    return None


def _normalize_text(value):
    return re.sub(r"\s+", "", str(value or ""))
