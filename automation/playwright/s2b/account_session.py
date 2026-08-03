from pathlib import Path
import json
import subprocess
import time
from urllib.error import URLError
from urllib.request import urlopen


CHROME_PATH = Path(
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
AUTH_DIR = Path(__file__).resolve().parents[1] / ".auth"
ACCOUNT_PORTS = {"DTF": 9223, "UV": 9224, "3D": 9225}
SHARED_DEBUG_PORT = 9222
S2B_HOST = "overseasfactory.s2bdiy.com"


def connect_s2b_account_chrome(playwright, start_url, account_name):
    account = normalize_s2b_account(account_name)
    port = _connection_port(account)
    profile = AUTH_DIR / f"s2b-{account.casefold()}-chrome"
    if not _chrome_is_connectable(port):
        _launch_chrome(start_url, profile, port)
        _wait_for_chrome(port)
    return playwright.chromium.connect_over_cdp(
        f"http://127.0.0.1:{port}", timeout=30_000
    )


def _connection_port(account):
    # DTF historically shared the main Playwright Chrome on 9222. Reuse that
    # authenticated page when it is already open so existing users are not
    # forced into a second login session. UV and 3D stay isolated by account.
    if account == "DTF" and _chrome_has_s2b_page(SHARED_DEBUG_PORT):
        return SHARED_DEBUG_PORT
    return ACCOUNT_PORTS[account]


def normalize_s2b_account(account_name):
    account = str(account_name or "DTF").strip().upper()
    if account not in ACCOUNT_PORTS:
        raise ValueError(f"不支持的S2B账号：{account_name}")
    return account


def _launch_chrome(start_url, profile, port):
    if not CHROME_PATH.is_file():
        raise FileNotFoundError("未找到Google Chrome，请先安装Chrome")
    profile.parent.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            str(CHROME_PATH),
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            start_url,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _chrome_is_connectable(port):
    return bool(_chrome_targets(port))


def _chrome_has_s2b_page(port):
    return any(
        target.get("type") == "page"
        and S2B_HOST in str(target.get("url", ""))
        for target in _chrome_targets(port)
    )


def _chrome_targets(port):
    try:
        with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as response:
            targets = json.load(response)
        return [target for target in targets if target.get("type") == "page"]
    except (json.JSONDecodeError, URLError, TimeoutError):
        return []


def _wait_for_chrome(port):
    for _ in range(100):
        if _chrome_is_connectable(port):
            return
        time.sleep(0.1)
    raise TimeoutError("S2B专用Chrome启动超时")
