from pathlib import Path
import tomllib

from supabase import create_client

from db.automation_credentials import load_erp_token, save_erp_token


LOCAL_CREDENTIALS = (
    Path(__file__).resolve().parents[3]
    / ".streamlit"
    / "local_factory_credentials.toml"
)


def load_humbird_credentials(streamlit_secrets, platform, supabase=None):
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
    raise ValueError(
        f"未配置 {platform} API token；请先将管理员登录授权同步到数据库"
    )


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
