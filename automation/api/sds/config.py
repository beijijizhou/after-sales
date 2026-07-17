from pathlib import Path
import tomllib


LOCAL_USPS_SECRETS = (
    Path(__file__).resolve().parents[4]
    / "usps"
    / ".streamlit"
    / "secrets.toml"
)


def load_sds_credentials(streamlit_secrets, profile="2号线"):
    try:
        return dict(streamlit_secrets["factory_credentials"][profile])
    except KeyError:
        pass

    if LOCAL_USPS_SECRETS.exists():
        with LOCAL_USPS_SECRETS.open("rb") as file:
            local_secrets = tomllib.load(file)
        try:
            return dict(local_secrets["factory_credentials"][profile])
        except KeyError:
            pass

    raise ValueError(
        f"未找到 SDS factory_credentials.{profile} 配置"
    )
