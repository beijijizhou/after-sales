from pathlib import Path
import subprocess
import time
from urllib.error import URLError
from urllib.request import urlopen


AUTH_DIR = Path(__file__).parent / ".auth"
CHROME_PROFILE_DIR = AUTH_DIR / "haloo-chrome"
CHROME_PATH = Path(
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
DEBUG_PORT = 9222
CDP_URL = f"http://127.0.0.1:{DEBUG_PORT}"
HALOO_HOST = "haloopod.merchant.hihumbird.com"


def ensure_debug_chrome(start_url):
    if chrome_is_connectable():
        print("已连接当前 Chrome，不会打开新页面。", flush=True)
        return
    if not CHROME_PATH.exists():
        raise FileNotFoundError("未找到 Google Chrome，请先安装 Chrome")
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    print("正在启动可连接的 Google Chrome...", flush=True)
    subprocess.Popen([
        str(CHROME_PATH),
        f"--remote-debugging-port={DEBUG_PORT}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={CHROME_PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        start_url,
    ])
    wait_for_chrome()


def chrome_is_connectable():
    try:
        with urlopen(f"{CDP_URL}/json/version", timeout=1):
            return True
    except (URLError, TimeoutError):
        return False


def wait_for_chrome():
    for _ in range(100):
        if chrome_is_connectable():
            print("Google Chrome 已连接。", flush=True)
            return
        time.sleep(0.1)
    raise TimeoutError("Google Chrome 调试接口启动超时")


def find_haloo_page(browser):
    return find_erp_page(browser, HALOO_HOST, "Haloo")


def find_erp_page(browser, host, platform_name=None):
    pages = [page for context in browser.contexts for page in context.pages]
    platform_pages = [page for page in pages if host in page.url]
    if not platform_pages:
        name = platform_name or host
        raise RuntimeError(f"当前 Chrome 中没有找到{name}页面，请先打开并登录")
    return platform_pages[-1]
