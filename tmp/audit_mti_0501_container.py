import json

from db.supabase_client import supabase


columns = (
    "id,container_key,container_no,shipped_date,expected_arrival_date,"
    "actual_arrival_date,actual_arrival_at,department,category,brand,"
    "material,color,size,quantity,unit_cost,status,note,created_at"
)
rows = (
    supabase.table("inventory_container_imports")
    .select(columns)
    .eq("department", "DTF")
    .or_(
        "container_no.ilike.%MTI/05/01%,"
        "container_key.ilike.%MTI/05/01%,"
        "note.ilike.%MTI/05/01%"
    )
    .order("created_at")
    .limit(5000)
    .execute()
    .data
    or []
)
print(json.dumps(rows, ensure_ascii=False, indent=2))
