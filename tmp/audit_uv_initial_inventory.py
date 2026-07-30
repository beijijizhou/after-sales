import json
from collections import defaultdict

from db.supabase_client import supabase


FIELDS = (
    "id,department,category,brand,material,color,size,quantity_change,"
    "movement_date,reason,source_type,batch_id,reversal_of_batch_id,"
    "created_at,created_by"
)


rows = (
    supabase.table("inventory_movements")
    .select(FIELDS)
    .eq("department", "UV")
    .order("created_at")
    .limit(10000)
    .execute()
    .data
    or []
)

reversed_batches = {
    str(row["reversal_of_batch_id"])
    for row in rows
    if row.get("reversal_of_batch_id")
}
active = [
    row
    for row in rows
    if not row.get("reversal_of_batch_id")
    and str(row.get("batch_id") or "") not in reversed_batches
]
opening = [
    row
    for row in active
    if row.get("source_type") == "opening"
    or "初始化" in str(row.get("reason") or "")
]

batches = defaultdict(lambda: {
    "rows": 0,
    "total": 0,
    "movement_date": "",
    "created_at": "",
    "source_type": "",
    "reasons": set(),
    "items": [],
})
for row in active:
    batch_id = str(row.get("batch_id") or f"movement:{row['id']}")
    batch = batches[batch_id]
    batch["rows"] += 1
    batch["total"] += int(row.get("quantity_change") or 0)
    batch["movement_date"] = row.get("movement_date") or ""
    batch["created_at"] = row.get("created_at") or ""
    batch["source_type"] = row.get("source_type") or ""
    batch["reasons"].add(str(row.get("reason") or ""))
    batch["items"].append({
        "category": row.get("category"),
        "material": row.get("material"),
        "color": row.get("color"),
        "size": row.get("size"),
        "quantity_change": row.get("quantity_change"),
    })

batch_summary = []
for batch_id, batch in batches.items():
    batch["batch_id"] = batch_id
    batch["reasons"] = sorted(batch["reasons"])
    batch_summary.append(batch)
batch_summary.sort(key=lambda row: (row["created_at"], row["batch_id"]))

print(json.dumps({
    "movement_count": len(rows),
    "active_count": len(active),
    "reversed_batches": sorted(reversed_batches),
    "opening": opening,
    "batches": batch_summary,
    "positive_before_target_batch": [
        row for row in active
        if int(row.get("quantity_change") or 0) > 0
        and str(row.get("batch_id") or "")
        != "5e77f112-cbff-5cdd-8100-093d980737ad"
    ],
}, ensure_ascii=False, indent=2))
