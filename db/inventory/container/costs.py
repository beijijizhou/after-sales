from decimal import Decimal, InvalidOperation
from datetime import datetime
from zoneinfo import ZoneInfo

from db.finance.cost_maintenance import update_inbound_lot_cost
from db.inventory.container.workflow import extract_inventory_batch_id


EDITABLE_COST_STATUSES = {"未到货", "在途", "延迟", "已到柜"}


def normalize_container_unit_cost(value):
    try:
        cost = Decimal(str(value)).quantize(Decimal("0.0001"))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("成本必须是有效数字") from error
    if cost < 0:
        raise ValueError("成本不能小于 0")
    return float(cost)


def update_container_unit_cost(
    supabase, container_key, unit_cost, operated_by, note=""
):
    cost = normalize_container_unit_cost(unit_cost)
    rows = (
        supabase.table("inventory_container_imports")
        .select("id,container_no,status,unit_cost,quantity")
        .eq("container_key", container_key)
        .execute()
        .data
        or []
    )
    if not rows:
        raise ValueError("未找到货柜记录")
    statuses = {str(row.get("status") or "") for row in rows}
    if len(statuses) != 1:
        raise ValueError("同一货柜存在多个状态，请先检查数据")
    status = next(iter(statuses))
    if status not in EDITABLE_COST_STATUSES:
        raise ValueError("该货柜已入库或已取消，不能直接修改成本")

    previous_costs = sorted({
        normalize_container_unit_cost(row.get("unit_cost") or 0)
        for row in rows
    })
    (
        supabase.table("inventory_container_imports")
        .update({"unit_cost": cost, "成本": cost})
        .eq("container_key", container_key)
        .execute()
    )
    saved = (
        supabase.table("inventory_container_imports")
        .select("id,unit_cost")
        .eq("container_key", container_key)
        .execute()
        .data
        or []
    )
    if len(saved) != len(rows) or any(
        normalize_container_unit_cost(row.get("unit_cost") or 0) != cost
        for row in saved
    ):
        raise ValueError("成本保存后核验失败")

    container_no = rows[0].get("container_no") or container_key
    event_note = (
        f"单位成本：{previous_costs} → {cost:.4f}"
        + (f"｜{note.strip()}" if str(note).strip() else "")
    )
    try:
        supabase.table("inventory_container_events").insert({
            "container_key": container_key,
            "container_no": container_no,
            "event_type": "成本更正",
            "effective_date": datetime.now(
                ZoneInfo("America/New_York")
            ).date().isoformat(),
            "previous_status": status,
            "new_status": status,
            "operated_by": operated_by,
            "note": event_note,
        }).execute()
    except Exception:
        for row in rows:
            previous = normalize_container_unit_cost(
                row.get("unit_cost") or 0
            )
            (
                supabase.table("inventory_container_imports")
                .update({"unit_cost": previous, "成本": previous})
                .eq("id", row["id"])
                .execute()
            )
        raise
    return {
        "rows": len(saved),
        "quantity": sum(int(row.get("quantity") or 0) for row in rows),
        "unit_cost": cost,
    }


def update_container_item_costs(
    supabase, container_key, item_costs, operated_by
):
    normalized = {
        str(item_id): normalize_container_unit_cost(cost)
        for item_id, cost in item_costs.items()
    }
    if not normalized:
        return {"rows": 0}
    rows = (
        supabase.table("inventory_container_imports")
        .select("id,container_no,status,unit_cost")
        .eq("container_key", container_key)
        .execute()
        .data
        or []
    )
    by_id = {str(row["id"]): row for row in rows}
    missing = set(normalized) - set(by_id)
    if missing:
        raise ValueError(f"货柜明细不存在：{', '.join(sorted(missing))}")
    statuses = {str(row.get("status") or "") for row in rows}
    if len(statuses) != 1:
        raise ValueError("同一货柜存在多个状态，请先检查数据")
    status = next(iter(statuses))
    if status not in EDITABLE_COST_STATUSES:
        raise ValueError("该货柜已入库或已取消，不能直接修改成本")

    changed = {
        item_id: cost for item_id, cost in normalized.items()
        if normalize_container_unit_cost(
            by_id[item_id].get("unit_cost") or 0
        ) != cost
    }
    if not changed:
        return {"rows": 0}
    previous = {
        item_id: normalize_container_unit_cost(
            by_id[item_id].get("unit_cost") or 0
        )
        for item_id in changed
    }
    try:
        for item_id, cost in changed.items():
            (
                supabase.table("inventory_container_imports")
                .update({"unit_cost": cost, "成本": cost})
                .eq("id", item_id)
                .execute()
            )
        saved = (
            supabase.table("inventory_container_imports")
            .select("id,unit_cost")
            .eq("container_key", container_key)
            .execute()
            .data
            or []
        )
        saved_by_id = {str(row["id"]): row for row in saved}
        if any(
            normalize_container_unit_cost(
                saved_by_id[item_id].get("unit_cost") or 0
            ) != cost
            for item_id, cost in changed.items()
        ):
            raise ValueError("成本保存后核验失败")
        container_no = rows[0].get("container_no") or container_key
        summary = "；".join(
            f"{item_id[:8]}：{previous[item_id]:.4f}→{cost:.4f}"
            for item_id, cost in changed.items()
        )
        supabase.table("inventory_container_events").insert({
            "container_key": container_key,
            "container_no": container_no,
            "event_type": "成本更正",
            "effective_date": datetime.now(
                ZoneInfo("America/New_York")
            ).date().isoformat(),
            "previous_status": status,
            "new_status": status,
            "operated_by": operated_by,
            "note": f"明细成本自动保存｜{summary}",
        }).execute()
    except Exception:
        for item_id, cost in previous.items():
            (
                supabase.table("inventory_container_imports")
                .update({"unit_cost": cost, "成本": cost})
                .eq("id", item_id)
                .execute()
            )
        raise
    return {"rows": len(changed)}


def build_posted_container_cost_plan(rows, item_costs):
    normalized = {
        str(item_id): normalize_container_unit_cost(cost)
        for item_id, cost in item_costs.items()
    }
    plan = []
    for row in rows:
        item_id = str(row["id"])
        if item_id not in normalized:
            continue
        previous = normalize_container_unit_cost(row.get("unit_cost") or 0)
        target = normalized[item_id]
        if previous == target:
            continue
        plan.append({
            **row, "old_unit_cost": previous, "new_unit_cost": target,
        })
    desired_by_identity = {}
    for row in plan:
        desired_by_identity.setdefault(_cost_identity(row), set()).add(
            row["new_unit_cost"]
        )
    if any(len(costs) > 1 for costs in desired_by_identity.values()):
        raise ValueError("同一 SKU 在同一货柜中不能设置多个不同成本")
    return plan


def update_posted_container_item_costs(
    supabase, container_key, item_costs, operated_by,
):
    rows = (
        supabase.table("inventory_container_imports")
        .select(
            "id,container_no,status,department,category,brand,material,"
            "color,size,quantity,unit_cost"
        )
        .eq("container_key", container_key)
        .execute()
        .data
        or []
    )
    if not rows or any(row.get("status") != "已入库" for row in rows):
        raise ValueError("只有已入库货柜可以使用入库成本更正")
    plan = build_posted_container_cost_plan(rows, item_costs)
    if not plan:
        return {"rows": 0, "cost_lots": 0}

    events = (
        supabase.table("inventory_container_events")
        .select("note")
        .eq("container_key", container_key)
        .in_("event_type", ["入库", "入库后更正"])
        .execute()
        .data
        or []
    )
    batch_ids = list(dict.fromkeys(
        batch_id for batch_id in (
            extract_inventory_batch_id(event.get("note")) for event in events
        ) if batch_id
    ))
    movements = []
    if batch_ids:
        movements = (
            supabase.table("inventory_movements")
            .select(
                "id,batch_id,department,category,brand,material,color,size,"
                "quantity_change,unit_cost"
            )
            .in_("batch_id", batch_ids)
            .gt("quantity_change", 0)
            .execute()
            .data
            or []
        )
    movement_by_identity = {}
    for movement in movements:
        movement_by_identity.setdefault(_cost_identity(movement), []).append(
            movement
        )
    movement_ids = [movement["id"] for movement in movements]
    lots = []
    if movement_ids:
        lots = (
            supabase.table("inventory_cost_lots")
            .select("id,inbound_movement_id,unit_cost,reversed_at")
            .in_("inbound_movement_id", movement_ids)
            .is_("reversed_at", "null")
            .execute()
            .data
            or []
        )
    lots_by_movement = {}
    for lot in lots:
        lots_by_movement.setdefault(str(lot["inbound_movement_id"]), []).append(
            lot
        )

    changed_lots = []
    updated_rows = []
    try:
        for row in plan:
            related = movement_by_identity.get(_cost_identity(row), [])
            if not related:
                raise ValueError(
                    f"找不到对应入库流水：{row['material']} {row['color']} "
                    f"{row['size']}"
                )
            for movement in related:
                movement_lots = lots_by_movement.get(str(movement["id"]), [])
                if not movement_lots:
                    raise ValueError("对应入库流水没有成本批次，无法安全更正")
                for lot in movement_lots:
                    changed_lots.append({
                        "id": lot["id"],
                        "inbound_movement_id": movement["id"],
                        "old_unit_cost": lot.get("unit_cost"),
                    })
                    update_inbound_lot_cost(
                        supabase, lot["id"], row["new_unit_cost"]
                    )
            (
                supabase.table("inventory_container_imports")
                .update({
                    "unit_cost": row["new_unit_cost"],
                    "成本": row["new_unit_cost"],
                })
                .eq("id", row["id"])
                .execute()
            )
            updated_rows.append(row)

        details = "；".join(
            f"{row['brand']} {row['material']} {row['color']} {row['size']}："
            f"{row['old_unit_cost']:.4f}→{row['new_unit_cost']:.4f}"
            for row in plan
        )
        supabase.table("inventory_container_events").insert({
            "container_key": container_key,
            "container_no": rows[0].get("container_no") or None,
            "event_type": "入库成本更正",
            "effective_date": datetime.now(
                ZoneInfo("America/New_York")
            ).date().isoformat(),
            "previous_status": "已入库",
            "new_status": "已入库",
            "operated_by": operated_by,
            "note": details,
        }).execute()
    except Exception:
        for row in updated_rows:
            (
                supabase.table("inventory_container_imports")
                .update({
                    "unit_cost": row["old_unit_cost"],
                    "成本": row["old_unit_cost"],
                })
                .eq("id", row["id"])
                .execute()
            )
        for lot in changed_lots:
            old_cost = lot["old_unit_cost"]
            (
                supabase.table("inventory_cost_lots")
                .update({"unit_cost": old_cost})
                .eq("id", lot["id"])
                .execute()
            )
            (
                supabase.table("inventory_cost_allocations")
                .update({"unit_cost": old_cost})
                .eq("cost_lot_id", lot["id"])
                .is_("reversed_at", "null")
                .execute()
            )
            (
                supabase.table("inventory_movements")
                .update({
                    "unit_cost": old_cost,
                    "成本": old_cost,
                })
                .eq("id", lot["inbound_movement_id"])
                .execute()
            )
        raise
    return {"rows": len(plan), "cost_lots": len(changed_lots)}


def _cost_identity(row):
    return tuple(str(row.get(column) or "").strip() for column in [
        "department", "category", "brand", "material", "color", "size",
    ])
