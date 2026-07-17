import requests


LOGIN_URL = "https://factory-api.sdspod.com/login"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36"
)
REQUIRED_CREDENTIALS = (
    "contact_tel",
    "extraInfo",
    "factory_code",
    "password",
)


def login_sds_factory(credentials, session=None):
    missing = [key for key in REQUIRED_CREDENTIALS if not credentials.get(key)]
    if missing:
        raise ValueError(f"SDS2 登录配置缺少：{', '.join(missing)}")

    client = session or requests.Session()
    response = client.post(
        LOGIN_URL,
        json={key: credentials[key] for key in REQUIRED_CREDENTIALS},
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": USER_AGENT,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") or {}
    token = data.get("access_token") or data.get("token")
    factory_id = data.get("factory_id") or data.get("factoryId")
    if not token or not factory_id:
        raise ValueError("SDS2 登录成功，但响应中缺少 token 或工厂 ID")
    return client, token, factory_id
