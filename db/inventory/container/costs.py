from decimal import Decimal, InvalidOperation
from datetime import datetime
from zoneinfo import ZoneInfo


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
