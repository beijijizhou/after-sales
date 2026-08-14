"""Humbird Open Platform shipment adapter."""

from concurrent.futures import ThreadPoolExecutor, as_completed

from automation.api.humbird.open_client import HumbirdOpenApiClient


STAGE_STATUSES = {
    1: [-1],
    2: [1, 5],
    6: [9],
}


def fetch_humbird_shipments(
    platform,
    credentials,
    start_date,
    end_date,
    status=1,
    department="DTF",
):
    client = HumbirdOpenApiClient(credentials)
    items = client.production_items(
        start_date, end_date, statuses=STAGE_STATUSES.get(status)
    )
    orders = _group_orders(items, shipped_only=status == 6)
    rows = []
    with ThreadPoolExecutor(max_workers=min(12, max(1, len(orders)))) as pool:
        futures = {
            pool.submit(client.waybill, order_no): (order_no, order_items)
            for order_no, order_items in orders.items()
        }
        for future in as_completed(futures):
            order_no, order_items = futures[future]
            try:
                waybill = future.result()
            except Exception as error:
                if "不存在" in str(error) or "404" in str(error):
                    continue
                raise
            tracking = str(waybill.get("track_number") or "").strip()
            if not tracking:
                continue
            first = order_items[0]
            rows.append({
                "tenant_code": "default",
                "erp_platform": platform,
                "erp_account": platform,
                "department": department,
                "external_order_id": order_no,
                "merchant_order_id": str(first.get("order_third_id") or ""),
                "tracking_number": tracking,
                "carrier": str(waybill.get("logistics_method_name") or ""),
                "erp_status": _erp_status(order_items),
                "label_url": waybill.get("url"),
                "backup_label_url": None,
                "local_acceptance_status": "未接单",
                "source_payload": {
                    "provider": "Humbird Open Platform",
                    "delivery_time": first.get("delivery_time"),
                    "waybill": waybill,
                    "production_item_codes": [
                        item.get("code") for item in order_items
                    ],
                },
            })
    return sorted(rows, key=lambda row: row["external_order_id"])


def _group_orders(items, shipped_only=False):
    result = {}
    for item in items:
        if shipped_only and not (
            item.get("delivery_time") or item.get("status") == 9
        ):
            continue
        order_no = str(item.get("order_no") or "").strip()
        if order_no:
            result.setdefault(order_no, []).append(item)
    return result


def _erp_status(items):
    if any(item.get("delivery_time") for item in items):
        return "已发货"
    statuses = {str(item.get("status") or "") for item in items}
    return ",".join(sorted(statuses))
