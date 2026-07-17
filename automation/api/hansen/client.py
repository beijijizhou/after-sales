from datetime import datetime, time, timedelta

from automation.api.hansen.auth import USER_AGENT, login_hansen_factory


DASHBOARD_URL = "https://tshirt.riin.com/manufacture/goodLabel/dashboard"
MAX_RECORDS = 50_000
LABEL_STATUSES = [-1, 1, 5, 10, 20, 30, 40, 80, 50]


def fetch_hansen_production_records(
    start_date,
    end_date,
    credentials,
    report_progress=None,
):
    report = report_progress or (lambda _message: None)
    report("1/3 正在登录汉森工厂接口")
    client, token = login_hansen_factory(credentials)
    start_at = datetime.combine(start_date - timedelta(days=1), time(18))
    end_at = datetime.combine(end_date, time(23, 59, 59))
    start_text = start_at.strftime("%Y-%m-%d %H:%M:%S")
    end_text = end_at.strftime("%Y-%m-%d %H:%M:%S")

    report("2/3 正在获取汉森生产数据（单次请求）")
    response = client.post(
        DASHBOARD_URL,
        json={
            "startTime": start_text,
            "endTime": end_text,
            "timeType": 2,
            "time": [start_text, end_text],
            "extraBizStatuses": [101, 0],
            "pageIndex": 1,
            "pageSize": MAX_RECORDS,
            "labelStatusList": LABEL_STATUSES,
            "timeoutFlag": None,
            "sortRule": "asc",
        },
        headers=_dashboard_headers(token),
        timeout=90,
    )
    response.raise_for_status()
    data = (response.json().get("data") or {})
    records = data.get("records") or []
    total = int(data.get("total") or len(records))
    if len(records) < total:
        raise ValueError(
            f"汉森应返回 {total:,} 条，实际仅收到 {len(records):,} 条"
        )
    report(f"3/3 汉森数据接收完成：{len(records):,} 条")
    return records


def _dashboard_headers(token):
    return {
        "Accept": "application/json, text/plain, */*",
        "Authorization": token,
        "Content-Type": "application/json",
        "Origin": "https://tshirt.riin.com",
        "Referer": "https://tshirt.riin.com/",
        "User-Agent": USER_AGENT,
        "X-Requested-With": "XMLHttpRequest",
        "X-Time-Zone": "UTC-5",
    }
