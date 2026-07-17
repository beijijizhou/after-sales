import requests


LOGIN_URL = "https://tshirt.riin.com/auth/api/auth/login"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36"
)


def login_hansen_factory(credentials, session=None):
    required = ("username", "password", "client_id")
    missing = [key for key in required if not credentials.get(key)]
    if missing:
        raise ValueError(f"汉森登录配置缺少：{', '.join(missing)}")

    client = session or requests.Session()
    response = client.post(
        LOGIN_URL,
        json={
            "username": credentials["username"],
            "password": credentials["password"],
            "clientId": credentials["client_id"],
        },
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
    token = data.get("token") or data.get("accessToken")
    if not token:
        raise ValueError("汉森登录成功，但响应中缺少 token")
    return client, token
