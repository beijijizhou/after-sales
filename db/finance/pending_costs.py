import pandas as pd


COLUMNS = [
    "id", "business_date", "department", "category", "brand",
    "material", "color", "size", "quantity", "unit_cost",
    "inventory_effect", "status", "note", "created_by", "created_at",
]


def load_pending_cost_batches(supabase):
    try:
        rows = (
            supabase.table("inventory_pending_cost_batches")
            .select(",".join(COLUMNS))
            .in_("status", ["pending_review", "ready_to_allocate"])
            .order("business_date", desc=True)
            .order("created_at", desc=True)
            .execute()
            .data
        )
    except Exception as exc:
        if "inventory_pending_cost_batches" in str(exc) and "PGRST205" in str(exc):
            return pd.DataFrame(columns=COLUMNS)
        raise
    result = pd.DataFrame(rows, columns=COLUMNS)
    if not result.empty:
        result["quantity"] = pd.to_numeric(result["quantity"], errors="coerce").fillna(0)
        result["unit_cost"] = pd.to_numeric(result["unit_cost"], errors="coerce")
    return result


def update_pending_cost_batch(supabase, batch_id, unit_cost):
    value = float(unit_cost)
    if value <= 0:
        raise ValueError("单位成本必须大于 0")
    response = (
        supabase.table("inventory_pending_cost_batches")
        .update({"unit_cost": value, "status": "ready_to_allocate"})
        .eq("id", batch_id)
        .in_("status", ["pending_review", "ready_to_allocate"])
        .execute()
    )
    if not response.data:
        raise ValueError("找不到可更新的待核价批次")
    return response.data[0]
