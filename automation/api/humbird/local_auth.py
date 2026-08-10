"""Refresh Humbird API tokens from the project-owned Chrome session.

The token is copied only into the git-ignored local credentials file.  It is
never returned from the public helper or written to stdout/logging.
"""

from pathlib import Path
import os
import tempfile

from playwright.sync_api import sync_playwright

from automation.api.humbird.config import LOCAL_CREDENTIALS
from automation.api.humbird.config import save_humbird_credentials
from automation.playwright.chrome_session import (
    chrome_is_connectable,
    connect_debug_chrome,
    find_erp_page,
)
from automation.playwright.haloo.platforms import get_erp_platform


TOKEN_STORAGE_KEY = "factory_token_"


class HumbirdLocalLoginRequired(RuntimeError):
    pass


def refresh_local_humbird_token(platform):
    """Capture one logged-in token and persist it without exposing its value."""
    erp = get_erp_platform(platform)
    was_running = chrome_is_connectable()

    with sync_playwright() as playwright:
        browser = connect_debug_chrome(playwright, erp.production_items_url)
        page = find_erp_page(
            browser,
            erp.host,
            erp.name,
            erp.production_items_url,
        )
        if "/login" in page.url:
            raise HumbirdLocalLoginRequired(
                f"{platform} 登录已失效；请完成一次人工登录后重试"
            )
        token = str(
            page.evaluate(
                "key => window.localStorage.getItem(key) || ''",
                TOKEN_STORAGE_KEY,
            )
            or ""
        ).strip()
        if not token:
            raise HumbirdLocalLoginRequired(
                f"{platform} 当前会话没有 API token；请重新登录后重试"
            )

    _save_token(platform, token)
    return {
        "platform": platform,
        "saved": True,
        "reused_running_browser": was_running,
    }


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
