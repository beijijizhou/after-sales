from datetime import datetime, time

import requests

from automation.integrations.carriers import is_usps_shipment
from automation.integrations.stages import (
    IN_PRODUCTION,
    SHIPPED,
    UNACCEPTED,
    stage_label,
)


ORDERS_URL = (
    "https://overseasfactory.s2bdiy.com/req/factory/"
    "orderProductOrder/getOrderList"
)
LABEL_URL = "https://overseasfactory.s2bdiy.com/req/factory/delivery/goodsDeliveryPrint"
PENDING_STATUS = UNACCEPTED
PAGE_SIZE = 1000
DATE_FIELD_BY_STAGE = {
    UNACCEPTED: "created_at",
    IN_PRODUCTION: "confirm_time",
    SHIPPED: "produced_time",
}


class S2BAuthenticationError(RuntimeError):
    pass


def fetch_s2b_pending_shipments(
    account_name,
    account,
    max_pages=100,
    status=PENDING_STATUS,
    start_date=None,
    end_date=None,
    report_progress=None,
):
    report = report_progress or (lambda _message: None)
    token = account["token"]
    client = requests.Session()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
    }
    results = []
    date_field = DATE_FIELD_BY_STAGE.get(status, "created_at")
    if start_date and end_date:
        report(
            f"S2B按{_date_field_label(date_field)}筛选："
            f"{start_date:%Y-%m-%d} 至 {end_date:%Y-%m-%d}。"
        )
    for page in range(1, max_pages + 1):
        response = client.post(
            ORDERS_URL, headers=headers,
            json=_order_payload(
                page, status, start_date=start_date, end_date=end_date,
            ),
            timeout=30,
        )
        if response.status_code in {401, 403}:
            raise S2BAuthenticationError("S2B登录已失效")
        response.raise_for_status()
        body = response.json()
        message = str(body.get("message") or body.get("msg") or "")
        if "非法登录" in message or "unauth" in message.casefold():
            raise S2BAuthenticationError("S2B登录已失效")
        data = body.get("data") or {}
        if not isinstance(data, dict):
            raise RuntimeError(message or "S2B订单接口返回异常")
        orders = data.get("data") or []
        results.extend(_normalize_order(order, account_name) for order in orders)
        report(
            f"S2B订单接口第 {page}/{int(data.get('last_page') or page)} 页："
            f"累计 {len(results):,}/{int(data.get('total') or len(results)):,} 条。"
        )
        if not orders or page >= int(data.get("last_page") or page):
            break
    before_filter = len(results)
    if start_date and end_date:
        results = [
            row for row in results
            if _row_in_date_range(
                row, date_field, start_date, end_date
            )
        ]
        report(
            f"S2B日期二次校验：接口返回 {before_filter:,} 条，"
            f"范围内 {len(results):,} 条。"
        )
    rows = [row for row in results if row["tracking_number"]]
    for row in rows:
        row["local_acceptance_status"] = stage_label(status)
    return rows


def _order_payload(
    page, status=PENDING_STATUS, start_date=None, end_date=None,
):
    payload = {
        "page": page,
        "per_page": PAGE_SIZE,
        "status": status,
        "order_code": [],
    }
    if start_date and end_date:
        field = DATE_FIELD_BY_STAGE.get(status, "created_at")
        payload[f"{field}_before"] = datetime.combine(
            start_date, time.min
        ).strftime("%Y-%m-%d %H:%M:%S")
        payload[f"{field}_after"] = datetime.combine(
            end_date, time.max
        ).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    return payload


def fetch_s2b_label(order_code, token):
    response = requests.post(
        LABEL_URL, params={"code": order_code},
        headers={"Authorization": f"Bearer {token}"}, timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _normalize_order(order, account_name):
    details = order.get("order_data") or order
    logistics = order.get("order_logistics") or details
    tracking = str(
        logistics.get("logisticss_track_number")
        or logistics.get("tracking_number") or ""
    ).strip()
    order_id = str(
        details.get("code") or details.get("order_code")
        or details.get("order_id") or order.get("id") or ""
    ).strip()
    account = str(account_name or "DTF").upper()
    department = account if account in {"UV", "3D"} else "DTF"
    return {
        "tenant_code": "default", "erp_platform": "S2B",
        "erp_account": account, "department": department,
        "external_order_id": order_id,
        "merchant_order_id": str(
            details.get("third_order_id") or details.get("order_no") or ""
        ),
        "tracking_number": tracking,
        "carrier": str(
            details.get("logistics_platform_name")
            or logistics.get("logistics_name") or ""
        ),
        "erp_status": str(details.get("status_text") or details.get("status") or 1),
        "label_url": details.get("logistics_label") or logistics.get("label_url"),
        "backup_label_url": None,
        "local_acceptance_status": "未接单", "source_payload": order,
    }


def _row_in_date_range(row, field, start_date, end_date):
    source = row.get("source_payload") or {}
    details = source.get("order_data") or source
    value = details.get(field)
    if not value:
        return False
    try:
        observed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    return start_date <= observed.date() <= end_date


def _date_field_label(field):
    return {
        "created_at": "派单时间",
        "confirm_time": "接单/创建生产计划时间",
        "produced_time": "生产完成时间",
    }.get(field, field)
