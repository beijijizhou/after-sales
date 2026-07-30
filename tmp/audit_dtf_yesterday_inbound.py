import json

from db.supabase_client import supabase


movements = (
    supabase.table("inventory_movements")
    .select(
        "id,department,category,brand,material,color,size,quantity_change,"
        "movement_date,reason,source_type,batch_id,reversal_of_batch_id,"
        "created_at,created_by"
    )
    .eq("department", "DTF")
    .gte("movement_date", "2026-07-28")
    .lte("movement_date", "2026-07-30")
    .order("created_at")
    .limit(10000)
    .execute()
    .data
    or []
)
items = (
    supabase.table("inventory_items")
    .select(
        "id,department,category,brand,material,color,size,quantity,"
        "unit,unit_cost,is_active"
    )
    .eq("department", "DTF")
    .order("category")
    .order("material")
    .order("color")
    .order("size")
    .limit(10000)
    .execute()
    .data
    or []
)
positive = [
    row for row in movements
    if int(row.get("quantity_change") or 0) > 0
    and not row.get("reversal_of_batch_id")
]
candidate_items = [
    row for row in items
    if row.get("category") == "黑白短袖"
    and str(row.get("brand") or "").casefold() == "haloo"
    and row.get("color") in {"黑", "白"}
]
print(json.dumps({
    "positive_movements": positive,
    "candidate_items": candidate_items,
}, ensure_ascii=False, indent=2))
