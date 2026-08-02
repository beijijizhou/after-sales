from pathlib import Path

from playwright.sync_api import sync_playwright

from automation.playwright.chrome_session import find_erp_page
from automation.playwright.s2b.account_session import (
    connect_s2b_account_chrome,
    normalize_s2b_account,
)
from automation.playwright.errors import ProductionLoginRequired
from automation.playwright.s2b.date_filter import apply_production_time_filter
from automation.playwright.s2b.exports import submit_and_download


S2B_HOST = "overseasfactory.s2bdiy.com"
S2B_PRODUCTION_URL = f"https://{S2B_HOST}/factory/billDetails"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOWNLOAD_DIR = PROJECT_ROOT / "output" / "automation" / "s2b" / "downloads"


def download_s2b_workbook(start_date, end_date, report, account_name="DTF"):
    account = normalize_s2b_account(account_name)
    report(f"1/7 正在连接本机Chrome：S2B {account}账号")
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = connect_s2b_account_chrome(
            playwright, S2B_PRODUCTION_URL, account
        )
        page = find_erp_page(
            browser, S2B_HOST, "S2B", S2B_PRODUCTION_URL
        )
        report("2/7 已找到 S2B，正在打开账单明细")
        if not page.url.startswith(S2B_PRODUCTION_URL):
            page.goto(S2B_PRODUCTION_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
        if "/login" in page.url:
            raise ProductionLoginRequired(
                f"请先在Chrome中完成S2B {account}账号登录和滑块验证"
            )

        report("3/7 正在筛选 S2B 生产时间")
        apply_production_time_filter(page, start_date, end_date, report)
        report("5/7 S2B 筛选完成")
        report("6/7 正在提交 S2B 条件导出")
        download = submit_and_download(page, report)
        report("7/7 已收到 S2B Excel，正在保存")
        return _save_download(download, start_date, end_date, account)


def _save_download(download, start_date, end_date, account_name="DTF"):
    filename = download.suggested_filename or (
        f"S2B_{account_name}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.xlsx"
    )
    destination = DOWNLOAD_DIR / f"{account_name}_{filename}"
    download.save_as(destination)
    return destination
