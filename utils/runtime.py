import os
from pathlib import Path


_TRUE_VALUES = {"1", "true", "yes", "on"}


def is_deployed_runtime(environ=None, project_path=None):
    """Identify production hosting without coupling business UI to one host."""
    values = os.environ if environ is None else environ
    app_environment = str(values.get("APP_ENV") or "").strip().lower()
    if app_environment in {"production", "prod", "deployment", "deployed"}:
        return True
    sharing_mode = str(
        values.get("STREAMLIT_SHARING_MODE") or ""
    ).strip().lower()
    if sharing_mode in _TRUE_VALUES:
        return True
    path = Path(project_path or __file__).resolve()
    return str(path).startswith("/mount/src/")
