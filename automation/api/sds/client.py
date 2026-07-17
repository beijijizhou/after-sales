from datetime import datetime

from automation.api.sds.auth import USER_AGENT, login_sds_factory


DETAIL_URL = "https://factory-api.sdspod.com/factoryOrderMonthBill/detail/page"
MAX_DAILY_RECORDS = 50_000


def fetch_sds_production_records(
    start_date,
    end_date,
    credentials,
    report_progress=None,
    platform="SDS",
):
    report = report_progress or (lambda _message: None)
    report(f"1/3 正在登录 {platform} 工厂接口")
    client, token, factory_id = login_sds_factory(credentials)

    report(f"2/3 正在获取 {platform} 生产完成数据（单次请求）")
    response = client.get(
        DETAIL_URL,
        params={
            "page": 1,
            "size": MAX_DAILY_RECORDS,
            "factoryId": factory_id,
            "startFinishDateTime": f"{start_date:%Y-%m-%d} 00:00:00",
            "endFinishDateTime": f"{end_date:%Y-%m-%d} 23:59:59",
            "t": int(datetime.now().timestamp() * 1000),
        },
        headers={
            "Accept": "*/*",
            "User-Agent": USER_AGENT,
            "access-token": token,
        },
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    records = payload.get("list") or []
    total = int(payload.get("totalCount") or len(records))
    if total > MAX_DAILY_RECORDS:
        raise ValueError(
            f"{platform} 返回 {total:,} 条，超过单次安全上限 "
            f"{MAX_DAILY_RECORDS:,} 条"
        )
    if len(records) < total:
        raise ValueError(
            f"{platform} 应返回 {total:,} 条，实际仅收到 {len(records):,} 条"
        )
    report(f"3/3 {platform} 数据接收完成：{len(records):,} 条")
    return records
