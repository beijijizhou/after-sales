from pathlib import Path
import tomllib


LOCAL_CREDENTIALS = (
    Path(__file__).resolve().parents[3]
    / ".streamlit"
    / "local_factory_credentials.toml"
)


def load_hansen_credentials(streamlit_secrets):
    try:
        return dict(streamlit_secrets["factory_credentials"]["汉森"])
    except KeyError:
        pass

    if LOCAL_CREDENTIALS.exists():
        with LOCAL_CREDENTIALS.open("rb") as file:
            local_secrets = tomllib.load(file)
        try:
            return dict(local_secrets["factory_credentials"]["汉森"])
        except KeyError:
            pass
    raise ValueError("未找到汉森 factory_credentials.汉森 配置")
