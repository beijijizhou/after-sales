from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd

from db.batches import BatchKind, BatchReference, reverse_batch
from db.inventory.operations.adjustments import (
    apply_adjustment_rows,
)

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


def build_posted_container_identity_correction_plan(
    rows, identity_updates, inventory,
):
    """Plan a SKU reclassification without increasing total inventory."""
    inventory_map = {
        _sku_key(row): int(row.get("quantity") or 0)
        for row in inventory
    }
    planned_identities = []
    plan = []
    for row in rows:
        item_id = str(row["id"])
        target = {
            column: str(
                identity_updates.get(item_id, {}).get(
                    column, row.get(column)
                ) or ""
            ).strip()
            for column in ["category", "brand", "material", "color", "size"]
        }
        if target["category"] != str(row.get("category") or "").strip():
            raise ValueError("已入库货柜SKU更正暂不支持跨品类移动")
        target_key = _sku_key({**row, **target})
        planned_identities.append(target_key)
        source_key = _sku_key(row)
        if target_key == source_key:
            continue
        available = inventory_map.get(source_key, 0)
        quantity = int(row.get("quantity") or 0)
        moved_quantity = min(quantity, available)
        inventory_map[source_key] = available - moved_quantity
        inventory_map[target_key] = (
            inventory_map.get(target_key, 0) + moved_quantity
        )
        plan.append({
            **row,
            "target": target,
            "moved_quantity": moved_quantity,
            "unresolved_history": quantity - moved_quantity,
        })
    if len(set(planned_identities)) != len(planned_identities):
        raise ValueError("更正后货柜中存在重复SKU明细")
    return plan


def correct_posted_container_identities(
    supabase, container_key, identity_updates, operated_by,
):
    """Reclassify posted cargo and its remaining stock as one audit batch."""
    rows = (
        supabase.table("inventory_container_imports").select(
            "id,container_no,status,department,category,brand,material,color,"
            "size,quantity,unit_cost"
        ).eq("container_key", container_key).execute().data or []
    )
    if not rows or any(row.get("status") != "已入库" for row in rows):
        raise ValueError("只有已入库货柜可以更正SKU归属")
    inventory = []
    for department in sorted({row["department"] for row in rows}):
        inventory.extend(
            supabase.table("inventory_items").select(
                "department,category,brand,material,color,size,quantity,is_active"
            ).eq("department", department).execute().data or []
        )
    active_keys = {
        _sku_key(row) for row in inventory if row.get("is_active", True)
    }
    plan = build_posted_container_identity_correction_plan(
        rows, identity_updates, inventory
    )
    for row in plan:
        if _sku_key({**row, **row["target"]}) not in active_keys:
            target = row["target"]
            raise ValueError(
                "目标SKU不存在或已停用："
                f"{target['material']} / {target['color']} / {target['size']}"
            )
    if not plan:
        return {"rows": 0, "inventory_change": 0, "unresolved_history": 0}

    batch_id = str(uuid4())
    today = datetime.now(ZoneInfo("America/New_York")).date()
    applied_groups = []
    try:
        adjustments = []
        for row in plan:
            quantity = row["moved_quantity"]
            if quantity <= 0:
                continue
            source_label = f"{row['material']}/{row['color']}/{row['size']}"
            target = row["target"]
            target_label = (
                f"{target['material']}/{target['color']}/{target['size']}"
            )
            common = {
                "日期": today,
                "数量": quantity,
                "备注": (
                    f"货柜入库SKU更正：{container_key}｜"
                    f"{source_label} → {target_label}"
                ),
            }
            adjustments.extend([
                {
                    **common, "操作": "扣减", "品牌": row["brand"],
                    "材质": row["material"], "颜色": row["color"],
                    "尺码": row["size"], "成本": pd.NA,
                    "department": row["department"],
                    "category": row["category"],
                },
                {
                    **common, "操作": "增加", "品牌": target["brand"],
                    "材质": target["material"], "颜色": target["color"],
                    "尺码": target["size"], "成本": row["unit_cost"],
                    "department": row["department"],
                    "category": target["category"],
                },
            ])
        frame = pd.DataFrame(adjustments)
        if not frame.empty:
            for (department, category), group in frame.groupby(
                ["department", "category"], dropna=False
            ):
                apply_adjustment_rows(
                    supabase, department, category,
                    group.drop(columns=["department", "category"]),
                    created_by=operated_by, source_type="bulk",
                    batch_id=batch_id,
                )
                applied_groups.append((department, category))
        for row in plan:
            target = row["target"]
            supabase.table("inventory_container_imports").update({
                **target,
                "品牌": target["brand"],
                "材质": target["material"],
            }).eq("id", row["id"]).execute()
        details = "；".join(
            f"{row['material']}/{row['color']}/{row['size']} → "
            f"{row['target']['material']}/{row['target']['color']}/"
            f"{row['target']['size']}，当前库存转移"
            f"{row['moved_quantity']}件，历史已消耗"
            f"{row['unresolved_history']}件"
            for row in plan
        )
        supabase.table("inventory_container_events").insert({
            "container_key": container_key,
            "container_no": rows[0].get("container_no") or container_key,
            "event_type": "入库后SKU更正",
            "effective_date": today.isoformat(),
            "previous_status": "已入库",
            "new_status": "已入库",
            "operated_by": operated_by,
            "note": f"{details}｜库存批次：{batch_id}",
        }).execute()
    except Exception:
        for row in plan:
            supabase.table("inventory_container_imports").update({
                "category": row["category"], "brand": row["brand"],
                "material": row["material"], "color": row["color"],
                "size": row["size"], "品牌": row["brand"],
                "材质": row["material"],
            }).eq("id", row["id"]).execute()
        if applied_groups:
            try:
                reverse_batch(
                    supabase,
                    BatchReference(
                        BatchKind.INVENTORY, batch_id,
                        applied_groups[0][0], applied_groups[0][1],
                    ),
                    operated_by,
                )
            except Exception:
                pass
        raise
    return {
        "rows": len(plan),
        "inventory_change": 0,
        "moved_quantity": sum(row["moved_quantity"] for row in plan),
        "unresolved_history": sum(
            row["unresolved_history"] for row in plan
        ),
        "batch_id": batch_id,
    }


def build_posted_container_correction_plan(rows, quantity_updates, inventory):
    inventory_map = {
        _sku_key(row): int(row.get("quantity") or 0)
        for row in inventory
    }
    plan = []
    for row in rows:
        item_id = str(row["id"])
        if item_id not in quantity_updates:
            continue
        old_quantity = int(row.get("quantity") or 0)
        new_quantity = int(quantity_updates[item_id])
        if new_quantity < 0:
            raise ValueError("货柜数量不能小于0")
        delta = new_quantity - old_quantity
        if delta == 0:
            continue
        available = inventory_map.get(_sku_key(row), 0)
        inventory_change = delta if delta > 0 else -min(abs(delta), available)
        inventory_map[_sku_key(row)] = available + inventory_change
        plan.append({
            **row,
            "old_quantity": old_quantity,
            "new_quantity": new_quantity,
            "delta": delta,
            "inventory_change": inventory_change,
            "unresolved_shortage": max(abs(delta) - available, 0)
            if delta < 0 else 0,
        })
    return plan


def correct_posted_container_quantities(
    supabase, container_key, quantity_updates, operated_by,
):
    rows = (supabase.table("inventory_container_imports").select(
        "id,container_no,status,department,category,brand,material,color,size,"
        "quantity,unit_cost"
    ).eq("container_key", container_key).execute().data or [])
    if not rows or any(row.get("status") != "已入库" for row in rows):
        raise ValueError("只有已入库货柜可以使用入库后更正")
    departments = list({row["department"] for row in rows})
    inventory = []
    for department in departments:
        inventory.extend(
            supabase.table("inventory_items").select(
                "department,category,brand,material,color,size,quantity"
            ).eq("department", department).execute().data or []
        )
    plan = build_posted_container_correction_plan(
        rows, quantity_updates, inventory
    )
    if not plan:
        return {"rows": 0, "inventory_change": 0, "unresolved_shortage": 0}
    batch_id = str(uuid4())
    today = datetime.now(ZoneInfo("America/New_York")).date()
    applied = False
    try:
        adjustment_rows = [row for row in plan if row["inventory_change"]]
        adjustment_frame = pd.DataFrame(adjustment_rows)
        groups = (
            adjustment_frame.groupby(
                ["department", "category"], dropna=False
            )
            if not adjustment_frame.empty else []
        )
        for (department, category), group in groups:
            adjustments = pd.DataFrame({
                "日期": today,
                "操作": group["inventory_change"].map(
                    lambda value: "增加" if value > 0 else "扣减"
                ),
                "品牌": group["brand"], "材质": group["material"],
                "颜色": group["color"], "尺码": group["size"],
                "数量": group["inventory_change"].abs(),
                "成本": group["unit_cost"].where(
                    group["inventory_change"] > 0, pd.NA
                ),
                "备注": f"货柜入库更正：{container_key}",
            })
            apply_adjustment_rows(
                supabase, department, category, adjustments,
                created_by=operated_by, source_type="bulk", batch_id=batch_id,
            )
            applied = True
        for row in plan:
            supabase.table("inventory_container_imports").update({
                "quantity": row["new_quantity"]
            }).eq("id", row["id"]).execute()
        total_before = sum(row["old_quantity"] for row in plan)
        total_after = sum(row["new_quantity"] for row in plan)
        unresolved = sum(row["unresolved_shortage"] for row in plan)
        note = (
            f"入库后更正 {len(plan)} 行；变动 {total_after-total_before:+d} 件；"
            f"库存同步 {sum(row['inventory_change'] for row in plan):+d} 件；"
            f"已消耗历史差额 {unresolved} 件；库存批次：{batch_id}"
        )
        supabase.table("inventory_container_events").insert({
            "container_key": container_key,
            "container_no": rows[0].get("container_no") or container_key,
            "event_type": "入库后更正",
            "effective_date": today.isoformat(),
            "previous_status": "已入库", "new_status": "已入库",
            "operated_by": operated_by, "note": note,
        }).execute()
    except Exception:
        for row in plan:
            supabase.table("inventory_container_imports").update({
                "quantity": row["old_quantity"]
            }).eq("id", row["id"]).execute()
        if applied:
            try:
                reverse_batch(
                    supabase,
                    BatchReference(
                        BatchKind.INVENTORY, batch_id,
                        rows[0]["department"], rows[0]["category"],
                    ),
                    operated_by,
                )
            except Exception:
                pass
        raise
    return {
        "rows": len(plan),
        "inventory_change": sum(row["inventory_change"] for row in plan),
        "unresolved_shortage": sum(row["unresolved_shortage"] for row in plan),
        "batch_id": batch_id,
    }


def _sku_key(row):
    return tuple(str(row.get(column) or "").strip() for column in [
        "department", "category", "brand", "material", "color", "size",
    ])
