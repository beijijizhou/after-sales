import json

from db.supabase_client import supabase


CONTAINER = "COSU9507559060"
rows = (
    supabase.table("inventory_container_imports")
    .select(
        "id,container_key,container_no,shipped_date,expected_arrival_date,"
        "actual_arrival_date,department,category,brand,material,color,size,"
        "quantity,unit_cost,status,note,created_at"
    )
    .or_(
        f"container_no.eq.{CONTAINER},container_key.eq.{CONTAINER}"
    )
    .order("category")
    .order("brand")
    .order("material")
    .order("color")
    .order("size")
    .limit(5000)
    .execute()
    .data
    or []
)
print(json.dumps({
    "rows": rows,
    "count": len(rows),
    "total_quantity": sum(int(row.get("quantity") or 0) for row in rows),
    "cost_values": sorted({
        float(row.get("unit_cost") or 0) for row in rows
    }),
}, ensure_ascii=False, indent=2))
