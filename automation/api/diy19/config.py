from pathlib import Path
import tomllib


LOCAL_CREDENTIALS = (
    Path(__file__).resolve().parents[3]
    / ".streamlit"
    / "local_factory_credentials.toml"
)


def load_diy19_credentials(streamlit_secrets, platform):
    try:
        return dict(streamlit_secrets["factory_credentials"][platform])
    except KeyError:
        pass
    if LOCAL_CREDENTIALS.exists():
        with LOCAL_CREDENTIALS.open("rb") as file:
            local_secrets = tomllib.load(file)
        try:
            return dict(local_secrets["factory_credentials"][platform])
        except KeyError:
            pass
    raise ValueError(f"未找到{platform} factory_credentials.{platform} 配置")
