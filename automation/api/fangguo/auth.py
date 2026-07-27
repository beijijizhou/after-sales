import requests


LOGIN_URL = "https://fangguo.com/fgapp/basic/system/auth/login"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36"
)


def login_fangguo(credentials, session=None):
    required = ("username", "password", "tenant_id")
    missing = [key for key in required if not credentials.get(key)]
    if missing:
        raise ValueError(f"方果登录配置缺少：{', '.join(missing)}")

    client = session or requests.Session()
    response = client.post(
        LOGIN_URL,
        json={
            "loginSource": 0,
            "username": credentials["username"],
            "password": credentials["password"],
        },
        headers=_login_headers(credentials),
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") not in (None, 0, 200):
        raise ValueError(payload.get("msg") or "方果登录失败")

    token = _extract_token(payload)
    if not token:
        raise ValueError("方果登录成功，但响应中缺少 token")
    return client, _strip_bearer(token)


def _login_headers(credentials):
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Authorization": "Bearer null",
        "Content-Type": "application/json",
        "From-Client": "0",
        "Origin": "https://fangguo.com",
        "Referer": "https://fangguo.com/login",
        "Tenant-Id": str(credentials["tenant_id"]).strip(),
        "User-Agent": USER_AGENT,
        "X-Timezone-Offset": "America/New_York",
    }
    fingerprint = str(credentials.get("fingerprint") or "").strip()
    if fingerprint:
        headers["Fingerprint"] = fingerprint
    return headers


def _extract_token(payload):
    data = payload.get("data")
    candidates = [payload]
    if isinstance(data, dict):
        candidates.insert(0, data)
    elif isinstance(data, str):
        return data

    for source in candidates:
        for key in (
            "access_token", "accessToken", "token",
            "authorization", "Authorization",
        ):
            if source.get(key):
                return str(source[key])
    return ""


def _strip_bearer(token):
    value = str(token).strip()
    return value[7:].strip() if value.casefold().startswith("bearer ") else value
