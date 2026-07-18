from datetime import datetime, time
from math import ceil
from zoneinfo import ZoneInfo

import requests


API_URL = "https://fangguo.com/fgapp/order/factory/trade/page"
NEW_YORK = ZoneInfo("America/New_York")
PAGE_SIZE = 2_000


def fetch_fangguo_production_records(
    start_date,
    end_date,
    credentials,
    report_progress=None,
    start_hour=0,
    end_hour=23,
):
    report = report_progress or (lambda _message: None)
    headers = _build_headers(credentials)
    if not 0 <= start_hour <= 23 or not 0 <= end_hour <= 23:
        raise ValueError("方果查询小时必须在 0 至 23 之间")
    start_at = datetime.combine(start_date, time(start_hour), NEW_YORK)
    end_at = datetime.combine(
        end_date,
        time(end_hour, 59, 59, 999999),
        NEW_YORK,
    )
    if start_at > end_at:
        raise ValueError("方果查询结束时间不能早于开始时间")
    start_ms = _to_milliseconds(start_at)
    end_ms = _to_milliseconds(end_at)

    report("1/3 正在连接方果生产接口")
    first_page = _fetch_page(headers, 1, start_ms, end_ms, search_count=True)
    records = first_page.get("list") or []
    total = int(first_page.get("total") or len(records))
    page_count = max(1, ceil(total / PAGE_SIZE))

    report(f"2/3 方果共有 {total:,} 单，正在接收生产项")
    for page_no in range(2, page_count + 1):
        page = _fetch_page(headers, page_no, start_ms, end_ms)
        records.extend(page.get("list") or [])

    if len(records) < total:
        raise ValueError(
            f"方果应返回 {total:,} 单，实际仅收到 {len(records):,} 单"
        )
    report(f"3/3 方果数据接收完成：{len(records):,} 单")
    return records


def _fetch_page(headers, page_no, start_ms, end_ms, search_count=False):
    response = requests.post(
        API_URL,
        headers=headers,
        json=_build_payload(page_no, start_ms, end_ms, search_count),
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise ValueError(payload.get("msg") or "方果接口返回未知错误")
    return payload.get("data") or {}


def _build_headers(credentials):
    token = str(credentials.get("token") or "").strip()
    tenant_id = str(credentials.get("tenant_id") or "").strip()
    if not token or not tenant_id:
        raise ValueError("方果配置需要 token 和 tenant_id")
    if not token.casefold().startswith("bearer "):
        token = f"Bearer {token}"
    return {
        "Accept": "application/json, text/plain, */*",
        "Authorization": token,
        "Content-Type": "application/json",
        "From-Client": "0",
        "Origin": "https://fangguo.com",
        "Referer": "https://fangguo.com/factory/usual/orderList",
        "Tenant-Id": tenant_id,
        "X-Timezone-Offset": "America/New_York",
    }


def _build_payload(page_no, start_ms, end_ms, search_count):
    return {
        "pageNo": page_no,
        "pageSize": PAGE_SIZE,
        "statusType": 1,
        "pageType": 1,
        "tidStrs": "",
        "orderType": None,
        "timeTypeQuery": 1,
        "timeBegin": start_ms,
        "timeEnd": end_ms,
        "merchantIdList": [],
        "storeIdList": [],
        "channelCodeList": [],
        "flagListQuery": [],
        "cpNumStrs": "",
        "buyerNickStrs": "",
        "tradeIdStr": "",
        "barcode": "",
        "batchNo": "",
        "searchCount": search_count,
    }


def _to_milliseconds(value):
    return int(value.timestamp() * 1_000)
