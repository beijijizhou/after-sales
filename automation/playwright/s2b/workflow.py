from pathlib import Path

from playwright.sync_api import sync_playwright

from automation.playwright.chrome_session import (
    CDP_URL,
    ensure_debug_chrome,
    find_erp_page,
)
from automation.playwright.errors import ProductionLoginRequired
from automation.playwright.s2b.date_filter import apply_production_time_filter
from automation.playwright.s2b.exports import (
    download_row,
    find_export_record_page,
    find_ready_undownloaded_row,
    submit_and_download,
)


S2B_HOST = "overseasfactory.s2bdiy.com"
S2B_PRODUCTION_URL = f"https://{S2B_HOST}/factory/billDetails"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOWNLOAD_DIR = PROJECT_ROOT / "output" / "automation" / "s2b" / "downloads"


def download_s2b_workbook(start_date, end_date, report):
    report("1/7 正在连接本机 Chrome：S2B")
    ensure_debug_chrome(S2B_PRODUCTION_URL)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(CDP_URL)
        records_page = find_export_record_page(browser)
        ready_row = find_ready_undownloaded_row(records_page)
        if ready_row is not None:
            report("已找到 S2B 最新未下载 Excel，正在下载")
            download = download_row(records_page, ready_row)
            return _save_download(download, start_date, end_date)
        page = find_erp_page(
            browser, S2B_HOST, "S2B", S2B_PRODUCTION_URL
        )
        report("2/7 已找到 S2B，正在打开账单明细")
        if not page.url.startswith(S2B_PRODUCTION_URL):
            page.goto(S2B_PRODUCTION_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
        if "/login" in page.url:
            raise ProductionLoginRequired("请先在 Chrome 中完成 S2B 登录和滑块验证")

        report("3/7 正在筛选 S2B 生产时间")
        apply_production_time_filter(page, start_date, end_date, report)
        report("5/7 S2B 筛选完成")
        report("6/7 正在提交 S2B 条件导出")
        download = submit_and_download(page, report)
        report("7/7 已收到 S2B Excel，正在保存")
        return _save_download(download, start_date, end_date)


def _save_download(download, start_date, end_date):
    filename = download.suggested_filename or (
        f"S2B_{start_date:%Y%m%d}_{end_date:%Y%m%d}.xlsx"
    )
    destination = DOWNLOAD_DIR / filename
    download.save_as(destination)
    return destination
