from io import BytesIO

import pandas as pd

from automation.logistics.carriers import is_usps_shipment


S2B_LOGISTICS_COLUMNS = {
    "订单编码", "商户订单号", "物流方式", "物流单号", "订单状态",
}


def parse_s2b_logistics_workbook(file_bytes, account="DTF"):
    return parse_s2b_logistics_frame(pd.read_excel(BytesIO(file_bytes)), account)


def parse_s2b_logistics_frame(source, account="DTF"):
    missing = S2B_LOGISTICS_COLUMNS - set(source.columns)
    if missing:
        raise ValueError(
            "S2B Excel缺少物流字段：" + "、".join(sorted(missing))
        )
    rows = []
    for record in source.to_dict("records"):
        tracking = _text(record.get("物流单号"))
        order_id = _text(record.get("订单编码"))
        carrier = _text(record.get("物流方式"))
        if (
            not tracking or not order_id
            or not is_usps_shipment(carrier, tracking)
        ):
            continue
        rows.append({
            "tenant_code": "default", "erp_platform": "S2B",
            "erp_account": account,
            "department": (
                account.upper() if account.upper() in {"UV", "3D"} else "DTF"
            ),
            "external_order_id": order_id,
            "merchant_order_id": _text(record.get("商户订单号")),
            "tracking_number": tracking,
            "carrier": carrier,
            "erp_status": _text(record.get("订单状态")),
            "label_url": None, "backup_label_url": None,
            "local_acceptance_status": "待核对",
            "source_payload": {
                str(key): _text(value) for key, value in record.items()
            },
        })
    return rows


def _text(value):
    return "" if pd.isna(value) else str(value).strip()
