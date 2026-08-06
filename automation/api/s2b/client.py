from datetime import datetime, time
from zoneinfo import ZoneInfo

import requests


PRODUCTION_URL = (
    "https://overseasfactory.s2bdiy.com/req/factory/bill"
)
NEW_YORK = ZoneInfo("America/New_York")
PAGE_SIZE = 250


class S2BProductionAuthenticationError(RuntimeError):
    pass


def fetch_s2b_production_records(
    start_date,
    end_date,
    credentials,
    report_progress=None,
    start_hour=0,
    end_hour=23,
):
    report = report_progress or (lambda _message: None)
    token = str((credentials or {}).get("token") or "").strip()
    if not token:
        raise ValueError("S2B 生产接口缺少 token")
    start_at, end_at = new_york_production_bounds(
        start_date, end_date, start_hour, end_hour
    )
    client = requests.Session()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/plain, */*",
    }
    records = []
    expected_total = None
    last_page = 1
    page = 1
    report(
        "1/3 正在读取 S2B 生产接口："
        f"{start_at:%Y-%m-%d %H:%M:%S} 至 "
        f"{end_at:%Y-%m-%d %H:%M:%S}（纽约）"
    )
    while page <= last_page:
        response = client.get(
            PRODUCTION_URL,
            headers=headers,
            params=_production_params(start_at, end_at, page),
            timeout=30,
        )
        if response.status_code in {401, 403}:
            raise S2BProductionAuthenticationError("S2B 登录已失效")
        response.raise_for_status()
        body = response.json()
        message = str(body.get("message") or body.get("msg") or "")
        if "非法登录" in message or "unauth" in message.casefold():
            raise S2BProductionAuthenticationError("S2B 登录已失效")
        data = body.get("data") or {}
        if not isinstance(data, dict):
            raise RuntimeError(message or "S2B 生产接口返回异常")
        rows = data.get("data") or []
        if not isinstance(rows, list):
            raise RuntimeError(message or "S2B 生产明细格式异常")
        records.extend(rows)
        expected_total = int(data.get("total") or len(records))
        last_page = int(data.get("last_page") or page)
        report(
            f"2/3 S2B 生产接口第 {page}/{last_page} 页："
            f"累计 {len(records):,}/{expected_total:,} 条"
        )
        page += 1
    if expected_total is not None and len(records) != expected_total:
        raise RuntimeError(
            f"S2B 生产接口应返回 {expected_total:,} 条，"
            f"实际收到 {len(records):,} 条"
        )
    report(f"3/3 S2B 生产数据接收完成：{len(records):,} 条")
    return records


def new_york_production_bounds(
    start_date, end_date, start_hour=0, end_hour=23,
):
    start_at = datetime.combine(
        start_date, time(int(start_hour), 0, 0), tzinfo=NEW_YORK
    )
    end_at = datetime.combine(
        end_date, time(int(end_hour), 59, 59), tzinfo=NEW_YORK
    )
    return start_at, end_at


def _production_params(start_at, end_at, page):
    return {
        "basic_product_ids": "",
        "order_status": "",
        "order_codes": "",
        "third_order_ids": "",
        "product_batch_numbers": "",
        "assigned_at_before": "",
        "assigned_at_after": "",
        "production_at_before": start_at.strftime("%Y-%m-%d %H:%M:%S"),
        "production_at_after": end_at.strftime("%Y-%m-%d %H:%M:%S"),
        "shipped_at_before": "",
        "shipped_at_after": "",
        "page": int(page),
        "per_page": PAGE_SIZE,
    }
