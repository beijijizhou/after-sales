from pathlib import Path

from playwright.sync_api import sync_playwright

from automation.playwright.chrome_session import (
    CDP_URL,
    ensure_debug_chrome,
    find_erp_page,
)
from automation.playwright.haloo.diagnostics import save_control_diagnostics
from automation.playwright.haloo.exports import (
    close_stale_export_modal,
    download_export_row,
    find_export_records_page,
    find_matching_export_row,
    submit_and_download,
)
from automation.playwright.haloo.filters import apply_production_item_filter
from automation.playwright.haloo.platforms import get_erp_platform
from automation.playwright.errors import ProductionLoginRequired


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOWNLOAD_ROOT = PROJECT_ROOT / "output" / "automation" / "erp" / "downloads"


HalooLoginRequired = ProductionLoginRequired


def download_production_workbook(
    start_date, end_date=None, report_progress=None, platform="Haloo"
):
    end_date = end_date or start_date
    erp = get_erp_platform(platform)
    report = lambda message: _report(report_progress, message)
    report(f"1/7 正在连接本机 Chrome：{erp.name}")
    ensure_debug_chrome(erp.production_items_url)
    download_dir = DOWNLOAD_ROOT / erp.name
    download_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(CDP_URL)
        existing = find_export_records_page(browser, erp.host)
        row = _find_reusable_row(existing, start_date, end_date)
        if row is not None:
            report("已找到上次生成成功的导出记录，正在下载")
            download = download_export_row(existing, row)
            return _save_download(
                download, start_date, end_date, download_dir
            )

        page = find_erp_page(browser, erp.host, erp.name)
        report(f"2/7 已找到{erp.name}，正在打开生产项管理")
        if not page.url.startswith(erp.production_items_url):
            page.goto(erp.production_items_url, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
        if "/login" in page.url:
            raise HalooLoginRequired(
                f"请先在已打开的 Chrome 中完成{erp.name}登录"
            )

        try:
            close_stale_export_modal(page)
            apply_production_item_filter(page, start_date, end_date, report)
            report("6/7 数量检查通过，正在导出生产项（仅一次）")
            download = submit_and_download(
                page, start_date, end_date, report
            )
        except Exception:
            save_control_diagnostics(page)
            raise

        report("7/7 已收到 Excel，正在保存文件")
        return _save_download(download, start_date, end_date, download_dir)


def _find_reusable_row(page, start_date, end_date):
    if page is None:
        return None
    return find_matching_export_row(
        page, start_date, end_date, require_success=True
    )


def _save_download(download, start_date, end_date, download_dir):
    filename = download.suggested_filename or (
        f"生产项信息_{start_date:%Y%m%d}_{end_date:%Y%m%d}.xlsx"
    )
    destination = download_dir / filename
    download.save_as(destination)
    return destination


def _report(callback, message):
    if callback:
        callback(message)
