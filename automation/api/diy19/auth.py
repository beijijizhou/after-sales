import requests


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36"
)


def login_diy19(base_url, platform, credentials, session=None):
    missing = [key for key in ("username", "password") if not credentials.get(key)]
    if missing:
        raise ValueError(f"{platform}登录配置缺少：{', '.join(missing)}")
    client = session or requests.Session()
    response = client.post(
        f"{base_url}/AdminUser/Login?lang=zh_chs",
        data={
            "languageKind": "zh_chs",
            "loginID": credentials["username"],
            "password": credentials["password"],
            "captchaCode": "",
        },
        headers={
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "User-Agent": USER_AGENT,
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("Code") != 200 or "admin_token" not in client.cookies:
        raise ValueError(payload.get("Message") or f"{platform}登录失败")
    return client
