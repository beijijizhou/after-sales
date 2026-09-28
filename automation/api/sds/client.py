from datetime import datetime

from automation.api.sds.auth import USER_AGENT, login_sds_factory
from automation.api.sds.endpoints import (
    FACTORY_COMPAT_BASE_URL,
    FACTORY_PRIMARY_BASE_URL,
    sds_endpoint_urls,
)
from automation.api.sds.transport import request_with_sds_fallback
from utils.erp.time_range import build_hour_range


DETAIL_URLS = sds_endpoint_urls(
    "/factoryOrderMonthBill/detail/page",
    primary_base_url=FACTORY_PRIMARY_BASE_URL,
    compatibility_base_url=FACTORY_COMPAT_BASE_URL,
)
MAX_DAILY_RECORDS = 50_000


def fetch_sds_production_records(
    start_date,
    end_date,
    credentials,
    report_progress=None,
    platform="SDS",
    start_hour=0,
    end_hour=23,
):
    report = report_progress or (lambda _message: None)
    report(f"1/3 正在登录 {platform} 工厂接口")
    client, token, factory_id = login_sds_factory(
        credentials, report_progress=report
    )
    start_at, end_at = build_hour_range(
        start_date, end_date, start_hour, end_hour
    )

    report(f"2/3 正在获取 {platform} 生产完成数据（单次请求）")
    response = request_with_sds_fallback(
        client,
        "get",
        DETAIL_URLS,
        report_progress=report,
        operation=f"{platform}生产数据读取",
        params={
            "page": 1,
            "size": MAX_DAILY_RECORDS,
            "factoryId": factory_id,
            "startFinishDateTime": f"{start_at:%Y-%m-%d %H:%M:%S}",
            "endFinishDateTime": f"{end_at:%Y-%m-%d %H:%M:%S}",
            "t": int(datetime.now().timestamp() * 1000),
        },
        headers={
            "Accept": "*/*",
            "User-Agent": USER_AGENT,
            "access-token": token,
        },
        timeout=90,
    )
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
