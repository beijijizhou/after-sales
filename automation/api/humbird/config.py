from pathlib import Path
import tomllib

from supabase import create_client

from db.automation_credentials import load_erp_token, save_erp_token
from db.automation_credentials import (
    CredentialDecryptionError,
    CredentialExpiredError,
)


LOCAL_CREDENTIALS = (
    Path(__file__).resolve().parents[3]
    / ".streamlit"
    / "local_factory_credentials.toml"
)


def load_humbird_credentials(streamlit_secrets, platform, supabase=None):
    open_api = _open_api_profile(streamlit_secrets, platform)
    try:
        legacy = _load_legacy_credentials(
            streamlit_secrets, platform, supabase
        )
    except Exception:
        if not open_api:
            raise
        legacy = None
    if open_api and legacy:
        return {
            **legacy,
            **open_api,
            "fallback_credential_source": legacy.get("credential_source"),
        }
    if open_api or legacy:
        return open_api or legacy
    raise ValueError(
        f"未配置 {platform} 开放平台 API Key 或备用 API token"
    )


def load_humbird_credentials_with_local_refresh(
    streamlit_secrets,
    platform,
    supabase=None,
    updated_by="admin-browser-refresh",
    report_progress=None,
):
    """Resolve credentials and refresh an unusable legacy token locally."""
    report = report_progress or (lambda _message: None)

    def refresh(reason):
        from automation.api.humbird.local_auth import (
            HumbirdLocalLoginRequired,
            local_humbird_login_available,
            refresh_local_humbird_token,
        )

        if not local_humbird_login_available():
            raise HumbirdLocalLoginRequired(
                f"{platform} Open API 和数据库 token 均不可用；"
                "当前云端不能启动浏览器，请管理员在本地同步一次刷新授权"
            ) from reason
        report(
            f"{platform} 数据库 token 不可用（{reason}）；"
            "第3级：启动本地专用 Chrome 刷新授权。"
        )
        refresh_local_humbird_token(
            platform,
            streamlit_secrets,
            supabase=supabase,
            updated_by=updated_by,
            report_progress=report_progress,
        )
        report("新 token 已加密写入数据库，正在继续本次生产同步。")
        refreshed = load_humbird_credentials(
            streamlit_secrets, platform, supabase
        )
        refreshed["_refresh_credentials"] = refresh
        return refreshed

    try:
        credentials = load_humbird_credentials(
            streamlit_secrets, platform, supabase
        )
    except (
        CredentialDecryptionError,
        CredentialExpiredError,
        ValueError,
    ) as error:
        return refresh(error)
    credentials["_refresh_credentials"] = refresh
    return credentials


def _load_legacy_credentials(streamlit_secrets, platform, supabase=None):
    database = _database_client(streamlit_secrets, supabase)
    encryption_secret = _encryption_secret(streamlit_secrets)
    if database is not None and encryption_secret:
        try:
            token = load_erp_token(database, platform, encryption_secret)
        except Exception as error:
            if "PGRST205" not in str(error):
                raise
            token = None
        if token:
            return {
                "token": token,
                "credential_source": "database",
                "credential_store": database,
                "encryption_secret": encryption_secret,
            }
    credentials = _profile(streamlit_secrets, platform)
    if credentials:
        return credentials
    if LOCAL_CREDENTIALS.exists():
        with LOCAL_CREDENTIALS.open("rb") as file:
            credentials = _profile(tomllib.load(file), platform)
        if credentials:
            return credentials
    return None


def save_humbird_credentials(
    streamlit_secrets,
    platform,
    token,
    supabase=None,
    updated_by="system",
):
    database = _database_client(streamlit_secrets, supabase)
    encryption_secret = _encryption_secret(streamlit_secrets)
    if database is None or not encryption_secret:
        raise ValueError("缺少 Supabase 服务端配置，无法共享 ERP token")
    save_erp_token(
        database,
        platform,
        token,
        encryption_secret,
        updated_by=updated_by,
    )


def _database_client(secrets, supplied):
    if supplied is not None:
        return supplied
    try:
        url = str(secrets["SUPABASE_URL"])
        key = str(secrets["SUPABASE_KEY"])
    except (KeyError, TypeError):
        return None
    return create_client(url, key)


def _encryption_secret(secrets):
    try:
        return str(
            secrets.get("ERP_TOKEN_ENCRYPTION_KEY")
            or secrets["SUPABASE_KEY"]
        ).strip()
    except (KeyError, TypeError, AttributeError):
        return ""


def _profile(secrets, platform):
    try:
        profile = dict(secrets["factory_credentials"][platform])
    except (KeyError, TypeError):
        return None
    token = str(profile.get("token") or "").strip()
    return {**profile, "token": token} if token else None


def _open_api_profile(secrets, platform):
    try:
        profile = dict(secrets["humbird_open_api"][platform])
    except (KeyError, TypeError):
        profile = {}
    api_key = str(
        profile.get("api_key")
        or (
            _secret_value(secrets, "HUMBIRD_OPEN_API_KEY")
            if platform == "Haloo"
            else ""
        )
    ).strip()
    if not api_key:
        return None
    return {
        "api_key": api_key,
        "credential_source": "humbird_open_api",
    }


def _secret_value(secrets, key):
    try:
        return secrets[key]
    except (KeyError, TypeError):
        return ""
