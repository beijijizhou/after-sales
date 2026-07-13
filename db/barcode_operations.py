from db.supabase_client import supabase


def normalize_barcode(value):
    return str(value).strip().upper()


def save_operation_rows(rows, username):
    records = []
    for row in rows:
        barcode = normalize_barcode(row.get("barcode"))
        operation_type = str(row.get("operation_type", "")).strip()
        if not barcode or not operation_type:
            continue

        records.append({
            "barcode": barcode,
            "operation_type": operation_type,
            "platform": str(row.get("platform", "") or "").strip() or None,
            "reason": str(row.get("reason", "") or "").strip(),
            "note": str(row.get("note", "") or "").strip(),
            "requires_rescan": bool(row.get("requires_rescan", True)),
            "created_by": username,
        })

    if not records:
        return None

    return supabase.table("barcode_operation_history").insert(records).execute()


def load_platform_options():
    response = (
        supabase
        .table("platforms")
        .select("name,sort_order")
        .eq("is_active", True)
        .order("sort_order")
        .order("name")
        .execute()
    )
    return [
        str(row.get("name", "")).strip()
        for row in response.data
        if str(row.get("name", "")).strip()
    ]
