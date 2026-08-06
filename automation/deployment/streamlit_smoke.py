from argparse import ArgumentParser
from pathlib import Path
import sys
import time
from urllib.parse import quote

from playwright.sync_api import sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "https://after-sales-dash.streamlit.app"
FATAL_TEXT = (
    "this app has encountered an error",
    "error running app",
    "uncaught app execution",
    "modulenotfounderror",
    "importerror",
    "traceback (most recent call last)",
)


def build_page_urls(base_url=DEFAULT_BASE_URL, pages_dir=None):
    pages_dir = Path(pages_dir or PROJECT_ROOT / "pages")
    base_url = str(base_url).rstrip("/")
    urls = [("主页", f"{base_url}/")]
    for page_file in sorted(pages_dir.glob("*.py")):
        route = page_file.stem.split("_", 1)[-1]
        urls.append((route, f"{base_url}/{quote(route)}"))
    return urls


def page_error_message(body_text, exception_texts=()):
    details = [str(value).strip() for value in exception_texts if value]
    if details:
        return " | ".join(details)
    normalized = str(body_text or "").casefold()
    matched = next((text for text in FATAL_TEXT if text in normalized), None)
    return matched or ""


def inspect_deployed_page(page, name, url):
    page.goto(url, wait_until="domcontentloaded", timeout=120_000)
    page.wait_for_timeout(2_500)
    wake_button = page.get_by_text("Yes, get this app back up!", exact=False)
    if wake_button.count():
        wake_button.first.click()
        page.wait_for_timeout(10_000)
    body_text = page.locator("body").inner_text(timeout=30_000)
    exception_texts = page.locator(
        '[data-testid="stException"], [data-testid="stAppError"]'
    ).all_inner_texts()
    error = page_error_message(body_text, exception_texts)
    if error:
        raise RuntimeError(f"{name}：{error}")


def run_deployed_smoke(base_url, wait_seconds=300, initial_delay=75):
    if initial_delay:
        print(f"等待 Streamlit Cloud 更新：{initial_delay} 秒", flush=True)
        time.sleep(initial_delay)
    deadline = time.monotonic() + wait_seconds
    pending = build_page_urls(base_url)
    last_errors = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        while pending and time.monotonic() < deadline:
            failed = []
            for name, url in pending:
                try:
                    inspect_deployed_page(page, name, url)
                    print(f"通过：{name}", flush=True)
                    last_errors.pop(name, None)
                except Exception as error:
                    last_errors[name] = str(error)
                    failed.append((name, url))
                    print(f"等待重试：{error}", flush=True)
            pending = failed
            if pending and time.monotonic() < deadline:
                time.sleep(15)
        browser.close()

    if pending:
        detail = "\n".join(
            f"- {name}: {last_errors.get(name, '页面未通过')}"
            for name, _url in pending
        )
        raise RuntimeError(f"线上页面烟雾测试失败：\n{detail}")


def main(argv=None):
    parser = ArgumentParser(description="逐页检查 Streamlit 线上部署")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--wait-seconds", type=int, default=300)
    parser.add_argument("--initial-delay", type=int, default=75)
    args = parser.parse_args(argv)
    try:
        run_deployed_smoke(
            args.base_url,
            wait_seconds=args.wait_seconds,
            initial_delay=args.initial_delay,
        )
    except Exception as error:
        print(error, file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
