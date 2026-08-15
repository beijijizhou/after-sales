from datetime import datetime, timezone

import pandas as pd


SHIPMENT_COLUMNS = (
    "id,tenant_code,erp_platform,erp_account,department,external_order_id,"
    "merchant_order_id,tracking_number,carrier,erp_status,label_url,"
    "backup_label_url,local_acceptance_status,first_seen_at,last_seen_at,"
    "source_payload"
)


def upsert_shipments(supabase, rows):
    if not rows:
        return []
    now = datetime.now(timezone.utc).isoformat()
    payload = [
        {**row, "last_seen_at": now}
        for row in _merge_shipment_rows(rows)
    ]
    return (
        supabase.table("logistics_shipments")
        .upsert(
            payload,
            on_conflict=(
                "tenant_code,erp_platform,erp_account,external_order_id,"
                "tracking_number"
            ),
        )
        .execute().data
    )


def _merge_shipment_rows(rows):
    merged = {}
    order = []
    for row in rows:
        identity = tuple(str(row.get(column) or "") for column in (
            "tenant_code", "erp_platform", "erp_account",
            "external_order_id", "tracking_number",
        ))
        if identity not in merged:
            merged[identity] = dict(row)
            merged[identity]["source_payload"] = {
                "items": _payload_items(row.get("source_payload"))
            }
            order.append(identity)
            continue

        shipment = merged[identity]
        shipment["source_payload"]["items"].extend(
            _payload_items(row.get("source_payload"))
        )
        for column in (
            "department", "merchant_order_id", "carrier", "erp_status",
            "label_url", "backup_label_url", "local_acceptance_status",
        ):
            if not shipment.get(column) and row.get(column):
                shipment[column] = row[column]
    return [merged[identity] for identity in order]


def _payload_items(payload):
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return list(payload["items"])
    return [payload or {}]


def load_shipments(supabase, tenant_code="default", limit=5000):
    rows = (
        supabase.table("logistics_shipments").select(SHIPMENT_COLUMNS)
        .eq("tenant_code", tenant_code)
        .order("last_seen_at", desc=True).limit(limit).execute().data
    )
    return pd.DataFrame(rows)


def load_shipments_by_tracking(supabase, tracking_numbers, tenant_code="default"):
    if not tracking_numbers:
        return pd.DataFrame()
    rows = (
        supabase.table("logistics_shipments").select(SHIPMENT_COLUMNS)
        .eq("tenant_code", tenant_code)
        .in_("tracking_number", list(tracking_numbers))
        .order("last_seen_at", desc=True).execute().data
    )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.drop_duplicates("tracking_number", keep="first")


def load_all_shipments_by_tracking(
    supabase, tracking_numbers, tenant_code="default",
):
    if not tracking_numbers:
        return pd.DataFrame()
    rows = (
        supabase.table("logistics_shipments").select(SHIPMENT_COLUMNS)
        .eq("tenant_code", tenant_code)
        .in_("tracking_number", list(tracking_numbers))
        .order("last_seen_at", desc=True).execute().data
    )
    return pd.DataFrame(rows)


def load_latest_label_reviews(supabase, shipment_ids):
    if not shipment_ids:
        return pd.DataFrame()
    rows = (
        supabase.table("logistics_label_reviews").select("*")
        .in_("shipment_id", list(shipment_ids))
        .order("created_at", desc=True).execute().data
    )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.drop_duplicates("shipment_id", keep="first")


def save_label_review(
    supabase, shipment_id, fields, reviewer, label_url=None,
    ocr_status="已识别", ocr_error="", engine_version="rapidocr-v4",
):
    fields = dict(fields or {})
    reasons = [
        f"OCR confidence: {fields.pop('ocr_confidence', 0):.4f}",
        "寄件地址和重量来自ERP面单PDF，不来自USPS Tracking API",
    ]
    if ocr_error:
        reasons.append(str(ocr_error))
    stored_fields = {
        key: fields.get(key) for key in (
            "label_content_hash", "extracted_street", "extracted_city",
            "extracted_state", "extracted_postal_code", "extracted_weight_oz",
        )
    }
    payload = {
        "shipment_id": shipment_id,
        **stored_fields,
        "label_url": label_url,
        "ocr_status": ocr_status,
        "ocr_error": ocr_error or None,
        "ocr_engine_version": engine_version,
        "automatic_result": "OCR已识别" if ocr_status == "已识别" else "OCR失败",
        "automatic_reasons": reasons,
        "reviewed_by": reviewer,
    }
    return supabase.table("logistics_label_reviews").insert(payload).execute().data


def load_latest_tracking_checks(supabase, tracking_numbers, tenant_code="default"):
    if not tracking_numbers:
        return pd.DataFrame()
    rows = (
        supabase.table("logistics_tracking_checks").select("*")
        .eq("tenant_code", tenant_code)
        .in_("tracking_number", list(tracking_numbers))
        .order("checked_at", desc=True).execute().data
    )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.drop_duplicates("tracking_number", keep="first")


def save_tracking_checks(supabase, rows, created_by, tenant_code="default"):
    if not rows:
        return []
    checked_at = datetime.now(timezone.utc).isoformat()
    payload = [{
        **row, "tenant_code": tenant_code, "provider": "USPS",
        "checked_at": checked_at, "created_by": created_by,
    } for row in rows]
    return supabase.table("logistics_tracking_checks").insert(payload).execute().data
