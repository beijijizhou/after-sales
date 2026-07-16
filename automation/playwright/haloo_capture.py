from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from automation.playwright.chrome_session import (
    CDP_URL,
    ensure_debug_chrome,
    find_haloo_page,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "output" / "automation" / "haloo"
DEFAULT_URL = "https://haloopod.merchant.hihumbird.com/factory/login"
NY_TIMEZONE = ZoneInfo("America/New_York")


def parse_arguments():
    parser = ArgumentParser(description="打开并采集 Haloo 订单页面")
    parser.add_argument("--url", default=DEFAULT_URL, help="Haloo 页面地址")
    return parser.parse_args()


def capture_haloo_page(url):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(NY_TIMEZONE).strftime("%Y%m%d_%H%M%S")
    ensure_debug_chrome(url)
    print("请保持已登录的 Haloo 标签页打开。")
    input("准备好后按 Enter，脚本会自动寻找当前 Haloo 页面：")
    capture_open_haloo_page(timestamp)


def capture_open_haloo_page(timestamp):
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(CDP_URL)
        page = find_haloo_page(browser)
        screenshot_path = OUTPUT_DIR / f"haloo_{timestamp}.png"
        html_path = OUTPUT_DIR / f"haloo_{timestamp}.html"
        page.screenshot(path=screenshot_path, full_page=True)
        html_path.write_text(page.content(), encoding="utf-8")
        print(f"页面地址：{page.url}")
        print(f"截图：{screenshot_path}")
        print(f"页面结构：{html_path}")


if __name__ == "__main__":
    arguments = parse_arguments()
    capture_haloo_page(arguments.url)
