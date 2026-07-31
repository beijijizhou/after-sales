from datetime import datetime
from zoneinfo import ZoneInfo


EDITABLE_STATUSES = {"未到货", "在途", "延迟", "已到柜"}
EDITABLE_FIELDS = {
    "expected_arrival_date", "category", "brand", "material", "color",
    "size", "quantity", "unit_cost", "note",
}


def update_container_items(supabase, container_key, updates, operated_by):
    rows = (supabase.table("inventory_container_imports").select(
        "id,container_no,status,expected_arrival_date,category,brand,material,"
        "color,size,quantity,unit_cost,note"
    ).eq("container_key", container_key).execute().data or [])
    by_id = {str(row["id"]): row for row in rows}
    if not rows:
        raise ValueError("未找到货柜明细")
    if any(str(row.get("status") or "") not in EDITABLE_STATUSES for row in rows):
        raise ValueError("货柜已入库或取消，不能直接修改")
    changed = {}
    for item_id, values in updates.items():
        if item_id not in by_id:
            raise ValueError(f"货柜明细不存在：{item_id}")
        clean = {key: values[key] for key in EDITABLE_FIELDS if key in values}
        clean["quantity"] = int(clean.get("quantity", by_id[item_id]["quantity"]))
        clean["unit_cost"] = float(clean.get("unit_cost", by_id[item_id].get("unit_cost") or 0))
        if clean["quantity"] < 0 or clean["unit_cost"] < 0:
            raise ValueError("数量和成本不能小于 0")
        clean["品牌"] = clean.get("brand", "")
        clean["材质"] = clean.get("material", "")
        clean["成本"] = clean["unit_cost"]
        comparable = {key: clean[key] for key in EDITABLE_FIELDS if key in clean}
        if any(_value(by_id[item_id].get(k)) != _value(v) for k, v in comparable.items()):
            changed[item_id] = clean
    if not changed:
        return {"rows": 0}
    first = rows[0]
    try:
        for item_id, values in changed.items():
            supabase.table("inventory_container_imports").update(values).eq("id", item_id).execute()
        supabase.table("inventory_container_events").insert({
            "container_key": container_key,
            "container_no": first.get("container_no") or container_key,
            "event_type": "明细更正",
            "effective_date": datetime.now(ZoneInfo("America/New_York")).date().isoformat(),
            "previous_status": first.get("status"),
            "new_status": first.get("status"),
            "operated_by": operated_by,
            "note": f"修改货柜明细 {len(changed)} 行",
        }).execute()
    except Exception:
        for item_id in changed:
            previous = {
                key: by_id[item_id].get(key) for key in EDITABLE_FIELDS
            }
            previous["品牌"] = previous.get("brand") or ""
            previous["材质"] = previous.get("material") or ""
            previous["成本"] = previous.get("unit_cost") or 0
            supabase.table("inventory_container_imports").update(previous).eq("id", item_id).execute()
        raise
    return {"rows": len(changed)}


def _value(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return round(value, 4)
    return str(value).strip()
