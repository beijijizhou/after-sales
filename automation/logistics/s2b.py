import requests

from automation.logistics.carriers import is_usps_shipment


ORDERS_URL = (
    "https://overseasfactory.s2bdiy.com/req/factory/"
    "orderProductOrder/getOrderList"
)
LABEL_URL = "https://overseasfactory.s2bdiy.com/req/factory/delivery/goodsDeliveryPrint"
PENDING_STATUS = 1


class S2BAuthenticationError(RuntimeError):
    pass


def fetch_s2b_pending_shipments(
    account_name, account, max_pages=100, status=PENDING_STATUS,
):
    token = account["token"]
    client = requests.Session()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
    }
    results = []
    for page in range(1, max_pages + 1):
        response = client.post(
            ORDERS_URL, headers=headers,
            json=_order_payload(page, status), timeout=30,
        )
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
        if not orders or page >= int(data.get("last_page") or page):
            break
    return [row for row in results if row["tracking_number"]]


def _order_payload(page, status=PENDING_STATUS):
    return {
        "page": page,
        "per_page": 100,
        "status": status,
        "order_code": [],
    }


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
    department = "UV" if account_name.upper() == "UV" else "DTF"
    return {
        "tenant_code": "default", "erp_platform": "S2B",
        "erp_account": account_name, "department": department,
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
