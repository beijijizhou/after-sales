import json
import sys

from db.supabase_client import supabase


container_key = sys.argv[1]
rows = (
    supabase.table("inventory_container_imports")
    .select(
        "id,container_key,container_no,department,category,brand,material,"
        "color,size,quantity,unit_cost,status,note,actual_arrival_date"
    )
    .or_(
        f"container_key.eq.{container_key},container_no.eq.{container_key}"
    )
    .order("color")
    .order("size")
    .execute()
    .data
    or []
)
events = (
    supabase.table("inventory_container_events")
    .select(
        "event_type,effective_date,previous_status,new_status,note,created_at"
    )
    .eq("container_key", container_key)
    .order("created_at")
    .execute()
    .data
    or []
)
print(json.dumps({"rows": rows, "events": events}, ensure_ascii=False, indent=2))
