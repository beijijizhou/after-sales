from pathlib import Path
import tomllib


LEGACY_SECRETS = (
    Path(__file__).resolve().parents[3]
    / "usps" / ".streamlit" / "secrets.toml"
)


def load_sds_account(secrets, profile):
    factory = _section(secrets, "factory_credentials", profile)
    qa = _section(secrets, "qa_credentials", profile)
    if factory and qa:
        return {"factory": factory, "qa": qa}
    legacy = _legacy_secrets()
    factory = factory or _section(legacy, "factory_credentials", profile)
    qa = qa or _section(legacy, "qa_credentials", profile)
    if not factory or not qa:
        raise ValueError(f"未配置SDS {profile}的工厂账号和QA账号")
    return {"factory": factory, "qa": qa}


def load_s2b_account(secrets, account):
    for section_name in ("logistics_s2b_accounts", "s2b_accounts"):
        values = _section(secrets, section_name, account)
        if values and values.get("token"):
            return values
    raise ValueError(
        f"未配置S2B {account}账号；请在Secrets中设置"
        f" logistics_s2b_accounts.{account}.token"
    )


def load_usps_credentials(secrets):
    client_id = _value(secrets, "USPS_CLIENT_ID")
    client_secret = _value(secrets, "USPS_CLIENT_SECRET")
    if client_id and client_secret:
        return {"client_id": client_id, "client_secret": client_secret}
    legacy = _legacy_secrets()
    client_id = client_id or _value(legacy, "USPS_CLIENT_ID")
    client_secret = client_secret or _value(legacy, "USPS_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise ValueError("未配置USPS_CLIENT_ID和USPS_CLIENT_SECRET")
    return {"client_id": client_id, "client_secret": client_secret}


def _section(secrets, section_name, key):
    try:
        return dict(secrets[section_name][key])
    except (KeyError, TypeError):
        return None


def _value(secrets, key):
    try:
        return str(secrets[key]).strip()
    except (KeyError, TypeError):
        return ""


def _legacy_secrets():
    if not LEGACY_SECRETS.is_file():
        return {}
    with LEGACY_SECRETS.open("rb") as file:
        return tomllib.load(file)
