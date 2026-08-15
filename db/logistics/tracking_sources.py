import pandas as pd

from db.logistics.repository import (
    load_all_shipments_by_tracking,
    upsert_shipments,
)


SOURCE_COLUMNS = (
    "id,check_id,shipment_id,department,erp_platform,erp_account,"
    "external_order_id,merchant_order_id,label_url,backup_label_url,created_at"
)


def ensure_tracking_context_shipments(supabase, context_rows, created_by):
    normalized = [_normalize_context(row, created_by) for row in context_rows]
    normalized = [row for row in normalized if row["tracking_number"]]
    if not normalized:
        return pd.DataFrame()
    numbers = list(dict.fromkeys(row["tracking_number"] for row in normalized))
    existing = load_all_shipments_by_tracking(supabase, numbers)
    missing = [
        row for row in normalized
        if not _matching_shipments(existing, row)
    ]
    created = pd.DataFrame(upsert_shipments(supabase, missing)) if missing else pd.DataFrame()
    if existing.empty:
        result = created
    elif created.empty:
        result = existing
    else:
        result = pd.concat([existing, created], ignore_index=True).drop_duplicates("id")
    backfill_tracking_check_sources(supabase, result)
    return result


def backfill_tracking_check_sources(supabase, shipments):
    if shipments is None or shipments.empty:
        return []
    numbers = [
        number for number in dict.fromkeys(
            shipments["tracking_number"].fillna("").astype(str)
        ) if number
    ]
    checks = _load_checks_by_tracking(supabase, numbers)
    return save_tracking_check_sources(supabase, checks, shipments)


def save_tracking_check_sources(supabase, saved_checks, shipments):
    if not saved_checks or shipments is None or shipments.empty:
        return []
    payload = []
    records = shipments.to_dict("records")
    for check in saved_checks:
        tracking_number = _text(check.get("tracking_number"))
        for shipment in records:
            if _text(shipment.get("tracking_number")) != tracking_number:
                continue
            payload.append({
                "check_id": check["id"],
                "shipment_id": shipment["id"],
                "department": _text(shipment.get("department")),
                "erp_platform": _text(shipment.get("erp_platform")),
                "erp_account": _text(shipment.get("erp_account")),
                "external_order_id": _text(shipment.get("external_order_id")),
                "merchant_order_id": _text(shipment.get("merchant_order_id")),
                "label_url": shipment.get("label_url"),
                "backup_label_url": shipment.get("backup_label_url"),
            })
    if not payload:
        return []
    saved = []
    for start in range(0, len(payload), 500):
        saved.extend(
            supabase.table("logistics_tracking_check_sources")
            .upsert(
                payload[start:start + 500],
                on_conflict="check_id,shipment_id",
            ).execute().data
        )
    return saved


def load_tracking_check_sources(supabase, check_ids):
    rows = []
    for start in range(0, len(check_ids), 200):
        chunk = list(check_ids[start:start + 200])
        if not chunk:
            continue
        rows.extend(
            supabase.table("logistics_tracking_check_sources")
            .select(SOURCE_COLUMNS).in_("check_id", chunk)
            .execute().data
        )
    return pd.DataFrame(rows)


def _load_checks_by_tracking(supabase, tracking_numbers):
    rows = []
    for start in range(0, len(tracking_numbers), 100):
        chunk = tracking_numbers[start:start + 100]
        for offset in range(0, 10000, 1000):
            page = (
                supabase.table("logistics_tracking_checks")
                .select("id,tracking_number").in_("tracking_number", chunk)
                .range(offset, offset + 999).execute().data
            )
            rows.extend(page)
            if len(page) < 1000:
                break
    return rows


def _matching_shipments(frame, context):
    if frame is None or frame.empty:
        return []
    matches = frame.loc[
        frame["tracking_number"].astype(str) == context["tracking_number"]
    ]
    order_id = context["external_order_id"]
    if order_id:
        matches = matches.loc[
            matches["external_order_id"].astype(str) == order_id
        ]
    return matches.to_dict("records")


def _normalize_context(row, created_by):
    tracking_number = _first(row, "物流单号", "tracking_number")
    order_id = _first(row, "订单号", "external_order_id")
    return {
        "tenant_code": "default",
        "erp_platform": _first(row, "ERP平台", "erp_platform") or "手工输入",
        "erp_account": _first(row, "ERP账号", "erp_account") or "manual",
        "department": _first(row, "部门", "department"),
        "external_order_id": order_id,
        "merchant_order_id": _first(row, "商户订单号", "merchant_order_id"),
        "tracking_number": tracking_number,
        "carrier": _first(row, "物流商", "carrier") or "USPS",
        "erp_status": "USPS手工查询",
        "label_url": row.get("面单PDF") or row.get("label_url") or None,
        "backup_label_url": (
            row.get("备用面单PDF") or row.get("backup_label_url") or None
        ),
        "local_acceptance_status": "待核对",
        "source_payload": {
            "source": "tracking_query_context",
            "created_by": _text(created_by),
        },
    }


def _first(row, *keys):
    return next((_text(row.get(key)) for key in keys if _text(row.get(key))), "")


def _text(value):
    if value is None or (not isinstance(value, (dict, list)) and pd.isna(value)):
        return ""
    return str(value).strip()
