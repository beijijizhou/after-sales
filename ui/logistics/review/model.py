"""Pure data transformations for logistics carrier and label review."""

from datetime import datetime
import random

from automation.logistics import (
    classify_carrier,
    classify_usps_subtype,
    usps_pickup_name,
)


def order_tracking_pairs(rows):
    pairs = []
    seen = set()
    for row in rows:
        pair = {
            "订单号": str(row.get("external_order_id") or "").strip(),
            "物流单号": str(row.get("tracking_number") or "").strip(),
        }
        optional = {
            "面单PDF": row.get("label_url"),
            "备用面单PDF": row.get("backup_label_url"),
            "ERP平台": row.get("erp_platform"),
            "面单OCR地址": row.get("ocr_address"),
            "重量（oz）": row.get("ocr_weight_oz"),
            "重量（lb）": row.get("ocr_weight_lb"),
            "OCR状态": row.get("ocr_status"),
        }
        pair.update({key: value for key, value in optional.items() if value})
        identity = (pair["订单号"], pair["物流单号"])
        if pair["物流单号"] and identity not in seen:
            pairs.append(pair)
            seen.add(identity)
    return pairs


def classify_carrier_rows(rows):
    reviewed = []
    for row in rows:
        carrier_family = classify_carrier(
            row.get("carrier"), row.get("tracking_number")
        )
        usps_subtype = classify_usps_subtype(
            row.get("carrier"), row.get("tracking_number"),
            row.get("source_payload"),
        )
        reviewed.append({
            "平台": row.get("erp_platform", ""),
            "账号": row.get("erp_account", ""),
            "Order ID": row.get("external_order_id", ""),
            "Tracking Number": row.get("tracking_number", ""),
            "平台物流方式": row.get("carrier", ""),
            "系统判断": carrier_family,
            "USPS子类型": usps_subtype,
            "实际揽收方": usps_pickup_name(usps_subtype),
            "面单": row.get("label_url"),
            "备用面单": row.get("backup_label_url"),
            "OCR寄件地址": row.get("ocr_address", ""),
            "OCR重量（oz）": row.get("ocr_weight_oz"),
            "OCR重量（lb）": row.get("ocr_weight_lb"),
            "OCR状态": row.get("ocr_status", ""),
            "row": row,
        })
    return reviewed


def label_ocr_candidates(reviewed):
    return [
        item for item in reviewed
        if item.get("row", {}).get("label_url")
        or item.get("row", {}).get("backup_label_url")
    ]


def is_target_usps_review(item):
    return (
        item.get("系统判断") == "USPS"
        and item.get("USPS子类型") == "普通USPS"
    )


def review_selection_defaults(rows, mode, random_count, random_seed):
    available_indices = [
        index for index, item in enumerate(rows)
        if label_ocr_candidates([item])
    ]
    if mode == "全选可下载":
        selected = set(available_indices)
    elif mode == "随机抽查" and available_indices:
        sample_size = min(max(0, random_count), len(available_indices))
        selected = set(random.Random(random_seed).sample(
            available_indices, sample_size
        ))
    else:
        selected = set()
    return [index in selected for index in range(len(rows))]


def label_documents(reviewed):
    return [{
        "url": item["row"].get("label_url")
        or item["row"].get("backup_label_url"),
        "platform": item.get("平台"),
        "order_id": item.get("Order ID"),
        "tracking_number": item.get("Tracking Number"),
    } for item in label_ocr_candidates(reviewed)]


def carrier_filter_name(row):
    subtype = row.get("USPS子类型")
    if subtype in {"CBS", "CBT"}:
        return subtype
    return row.get("系统判断", "其他待确认")


def default_logistics_platforms(platforms, connected_platforms):
    if "S2B" in platforms:
        return ["S2B"]
    return [
        platform for platform in platforms
        if platform in connected_platforms
    ][:1]


def erp_time_range(start_date, end_date):
    return {
        "startTime": datetime.combine(
            start_date, datetime.min.time()
        ).strftime("%Y-%m-%d %H:%M:%S"),
        "endTime": datetime.combine(
            end_date, datetime.max.time()
        ).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S"),
    }


def ocr_address(fields):
    return " ".join(str(fields.get(field) or "").strip() for field in (
        "extracted_street", "extracted_city", "extracted_state",
        "extracted_postal_code",
    )).strip()


def weight_lb(weight_oz):
    if weight_oz is None:
        return None
    return round(float(weight_oz) / 16, 4)


def database_error(error):
    detail = str(error)
    missing_relation = "does not exist" in detail or "schema cache" in detail
    if "logistics_usps_usage_events" in detail and missing_relation:
        return "USPS用量统计表尚未初始化，请运行 sql/logistics/02_usps_usage.sql。"
    if "logistics_" in detail and missing_relation:
        return "物流数据库尚未初始化，请先运行 sql/logistics/01_shipping_label_review.sql。"
    return f"物流数据库操作失败：{error}"


def build_ocr_summary(
    targets, available, candidates, skipped, pending, downloaded,
    total_seconds, ocr_seconds,
):
    address_ok = sum(
        bool(item["row"].get("ocr_address")) for item in candidates
    )
    weight_ok = sum(
        item["row"].get("ocr_weight_oz") is not None for item in candidates
    )
    return {
        "target": len(targets), "available": len(available),
        "processed": len(candidates), "skipped": len(skipped),
        "missing": len(targets) - len(available),
        "cache_hits": len(candidates) - len(pending),
        "downloaded": downloaded, "address_ok": address_ok,
        "weight_ok": weight_ok, "failed": len(candidates) - address_ok,
        "total_seconds": total_seconds, "ocr_seconds": ocr_seconds,
    }


def empty_ocr_summary(targets, available, skipped):
    if not targets:
        return None
    return {
        "target": len(targets), "available": len(available), "processed": 0,
        "skipped": len(skipped), "missing": len(targets), "cache_hits": 0,
        "downloaded": 0, "address_ok": 0, "weight_ok": 0, "failed": 0,
    }
