"""Refresh Humbird API tokens from the project-owned Chrome session.

The token is persisted to the ignored local file and, when configured, the
encrypted shared database. It is never returned or written to stdout/logging.
"""

from pathlib import Path
import os
import tempfile
from threading import Lock

from automation.api.humbird.config import LOCAL_CREDENTIALS
from automation.api.humbird.config import save_humbird_credentials
from automation.playwright.chrome_session import (
    chrome_is_connectable,
    connect_debug_chrome,
    find_erp_page,
)
from automation.playwright.haloo.platforms import get_erp_platform


LOGIN_WAIT_SECONDS = 180
TOKEN_CAPTURE_WAIT_SECONDS = 20
_BROWSER_REFRESH_LOCK = Lock()


class HumbirdLocalLoginRequired(RuntimeError):
    pass


def local_humbird_login_available():
    from automation.playwright.chrome_session import CHROME_PATH

    return CHROME_PATH.is_file()


def refresh_local_humbird_token(
    platform,
    streamlit_secrets=None,
    supabase=None,
    updated_by="admin-browser-refresh",
    report_progress=None,
):
    """Capture a login token and persist it locally and in the shared store."""
    if not local_humbird_login_available():
        raise HumbirdLocalLoginRequired(
            "当前部署环境不能启动本机浏览器；请由管理员在本地刷新授权"
        )
    report = report_progress or (lambda _message: None)
    report(f"{platform} 正在进入浏览器授权队列。")
    with _BROWSER_REFRESH_LOCK:
        token, was_running = _capture_browser_token(platform, report)

    _save_token(platform, token)
    database_saved = False
    if streamlit_secrets is not None:
        save_humbird_credentials(
            streamlit_secrets,
            platform,
            token,
            supabase=supabase,
            updated_by=updated_by,
        )
        database_saved = True
    return {
        "platform": platform,
        "saved": True,
        "database_saved": database_saved,
        "reused_running_browser": was_running,
    }


def _capture_browser_token(platform, report):
    from playwright.sync_api import sync_playwright

    erp = get_erp_platform(platform)
    was_running = chrome_is_connectable()
    captured = {}
    with sync_playwright() as playwright:
        browser = connect_debug_chrome(playwright, erp.production_items_url)
        page = find_erp_page(
            browser, erp.host, erp.name, erp.production_items_url,
        )

        def capture(request):
            authorization = str(
                request.headers.get("authorization") or ""
            ).strip()
            if (
                "hihumbird.com" in request.url
                and authorization.casefold().startswith("bearer ")
            ):
                captured["token"] = authorization[7:].strip()

        page.on("request", capture)
        if "/login" in page.url:
            report(
                f"{platform} 登录页已打开；正在等待人工登录，"
                f"最长 {LOGIN_WAIT_SECONDS // 60} 分钟。"
            )
            for elapsed in range(LOGIN_WAIT_SECONDS):
                page.wait_for_timeout(1000)
                if "/login" not in page.url:
                    report(f"{platform} 已检测到登录完成，正在捕获新 token。")
                    break
                if elapsed and elapsed % 15 == 0:
                    report(f"{platform} 仍在等待登录完成...（{elapsed}秒）")
            else:
                raise HumbirdLocalLoginRequired(
                    f"{platform} 等待登录超时；请完成登录后重新同步"
                )

        if not captured.get("token"):
            if page.url.startswith(erp.production_items_url):
                page.reload(wait_until="domcontentloaded")
            else:
                page.goto(erp.production_items_url, wait_until="domcontentloaded")
            for _ in range(TOKEN_CAPTURE_WAIT_SECONDS * 2):
                if captured.get("token"):
                    break
                page.wait_for_timeout(500)

        token = str(captured.get("token") or "").strip()
        if not token:
            raise HumbirdLocalLoginRequired(
                f"{platform} 登录完成但订单接口尚未发出请求；"
                "请确认生产列表已经显示后重新同步"
            )
        report(f"{platform} 已从真实 API 请求捕获新 token。")
        return token, was_running


def migrate_local_humbird_tokens_to_database(
    streamlit_secrets,
    platforms=("Haloo", "莆田", "隆丰"),
    supabase=None,
    updated_by="admin-local-migration",
):
    """Move locally captured tokens into the encrypted shared store."""
    profiles = _read_profiles()
    migrated = []
    for platform in platforms:
        token = str(profiles.get(platform, {}).get("token") or "").strip()
        if not token:
            continue
        save_humbird_credentials(
            streamlit_secrets,
            platform,
            token,
            supabase=supabase,
            updated_by=updated_by,
        )
        migrated.append(platform)
    return migrated


def _save_token(platform, token):
    existing = _read_profiles()
    existing[platform] = {**existing.get(platform, {}), "token": token}
    content = _serialize_profiles(existing)

    LOCAL_CREDENTIALS.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=".local_factory_credentials.",
        suffix=".tmp",
        dir=LOCAL_CREDENTIALS.parent,
        text=True,
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(content)
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, LOCAL_CREDENTIALS)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _read_profiles():
    if not LOCAL_CREDENTIALS.exists():
        return {}
    import tomllib

    with LOCAL_CREDENTIALS.open("rb") as file:
        payload = tomllib.load(file)
    return {
        str(name): dict(values)
        for name, values in payload.get("factory_credentials", {}).items()
    }


def _serialize_profiles(profiles):
    lines = []
    for platform in sorted(profiles):
        lines.append(f'[factory_credentials."{_escape(platform)}"]')
        for key, value in sorted(profiles[platform].items()):
            lines.append(f'{key} = "{_escape(value)}"')
        lines.append("")
    return "\n".join(lines)


def _escape(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')
