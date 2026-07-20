from pathlib import Path
import json
import os
import signal
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
        _safe_print("已连接当前 Chrome，不会打开新页面。")
        return
    if not CHROME_PATH.exists():
        raise FileNotFoundError("未找到 Google Chrome，请先安装 Chrome")
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    _safe_print("正在启动可连接的 Google Chrome...")
    _launch_debug_chrome(start_url)
    wait_for_chrome()


def _launch_debug_chrome(start_url):
    subprocess.Popen(
        [
            str(CHROME_PATH),
            f"--remote-debugging-port={DEBUG_PORT}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={CHROME_PROFILE_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
            start_url,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def connect_debug_chrome(playwright, start_url):
    ensure_debug_chrome(start_url)
    try:
        return playwright.chromium.connect_over_cdp(
            CDP_URL, timeout=15_000
        )
    except Exception as error:
        if not _is_recoverable_connection_error(error):
            raise
        _safe_print("专用 Chrome 连接异常，正在自动恢复...")
        restart_debug_chrome(start_url)
        return playwright.chromium.connect_over_cdp(
            CDP_URL, timeout=30_000
        )


def restart_debug_chrome(start_url):
    pid = _profile_chrome_pid()
    if pid is not None:
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            if not _process_exists(pid):
                break
            time.sleep(0.1)
        else:
            os.kill(pid, signal.SIGKILL)
            for _ in range(20):
                if not _process_exists(pid):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("专用 Chrome 无法停止，请手动关闭后重试")
    _launch_debug_chrome(start_url)
    wait_for_chrome()


def _profile_chrome_pid():
    lock = CHROME_PROFILE_DIR / "SingletonLock"
    if not lock.is_symlink():
        return None
    try:
        pid = int(os.readlink(lock).rsplit("-", 1)[-1])
    except (OSError, ValueError):
        return None
    process = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
        check=False,
    )
    return pid if str(CHROME_PROFILE_DIR) in process.stdout else None


def _process_exists(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _is_recoverable_connection_error(error):
    message = str(error).casefold()
    return "broken pipe" in message or "connect_over_cdp: timeout" in message


def chrome_is_connectable():
    try:
        with urlopen(f"{CDP_URL}/json/list", timeout=1) as response:
            targets = json.load(response)
        return any(target.get("type") == "page" for target in targets)
    except (json.JSONDecodeError, URLError, TimeoutError):
        return False


def wait_for_chrome():
    for _ in range(100):
        if chrome_is_connectable():
            _safe_print("Google Chrome 已连接。")
            return
        time.sleep(0.1)
    raise TimeoutError("Google Chrome 调试接口启动超时")


def _safe_print(message):
    try:
        print(message, flush=True)
    except BrokenPipeError:
        pass


def find_haloo_page(browser):
    return find_erp_page(browser, HALOO_HOST, "Haloo")


def find_erp_page(browser, host, platform_name=None, start_url=None):
    pages = [page for context in browser.contexts for page in context.pages]
    platform_pages = [page for page in pages if host in page.url]
    if not platform_pages:
        if start_url and browser.contexts:
            page = browser.contexts[0].new_page()
            page.goto(start_url, wait_until="domcontentloaded")
            return page
        name = platform_name or host
        raise RuntimeError(f"当前 Chrome 中没有找到{name}页面，请先打开并登录")
    return platform_pages[-1]
