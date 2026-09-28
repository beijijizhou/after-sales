import requests

from automation.api.sds.endpoints import (
    FACTORY_COMPAT_BASE_URL,
    FACTORY_PRIMARY_BASE_URL,
    sds_endpoint_urls,
)
from automation.api.sds.transport import request_with_sds_fallback

LOGIN_URLS = sds_endpoint_urls(
    "/login",
    primary_base_url=FACTORY_PRIMARY_BASE_URL,
    compatibility_base_url=FACTORY_COMPAT_BASE_URL,
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36"
)
REQUIRED_CREDENTIALS = (
    "contact_tel",
    "factory_code",
    "password",
)


def login_sds_factory(credentials, session=None, report_progress=None):
    missing = [key for key in REQUIRED_CREDENTIALS if not credentials.get(key)]
    if missing:
        raise ValueError(f"SDS 工厂登录配置缺少：{', '.join(missing)}")

    client = session or requests.Session()
    payload = {key: credentials[key] for key in REQUIRED_CREDENTIALS}
    payload["extraInfo"] = credentials.get("extraInfo") or ""
    response = request_with_sds_fallback(
        client,
        "post",
        LOGIN_URLS,
        report_progress=report_progress,
        operation="SDS工厂登录",
        json=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": USER_AGENT,
        },
        timeout=30,
    )
    payload = response.json()
    data = payload.get("data") or {}
    token = data.get("access_token") or data.get("token")
    factory_id = data.get("factory_id") or data.get("factoryId")
    if not token or not factory_id:
        raise ValueError("SDS 工厂登录成功，但响应中缺少 token 或工厂 ID")
    return client, token, factory_id
