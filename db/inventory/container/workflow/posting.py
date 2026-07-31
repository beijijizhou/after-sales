from uuid import uuid4
from datetime import datetime, timedelta, timezone

import pandas as pd

from db.inventory.container.workflow.state import (
    STATE_ARRIVED,
    STATE_IN_TRANSIT,
    STATE_POSTED,
    build_container_event,
    normalize_container_state,
    validate_container_transition,
)
from db.inventory.operations.adjustments import apply_adjustment_rows


def post_container_inventory(
    supabase, container_key, operated_by, note=""
):
    items = _load_container_rows(supabase, container_key)
    today = pd.Timestamp.now(tz="America/New_York").date()
    original = items[0]
    previous = normalize_container_state(original["status"])
    auto_arrival = previous == STATE_IN_TRANSIT
    if auto_arrival:
        validate_container_transition(previous, STATE_ARRIVED)
        previous = validate_container_transition(
            STATE_ARRIVED, STATE_POSTED
        )
    else:
        previous = validate_container_transition(previous, STATE_POSTED)
    _ensure_not_posted(supabase, container_key)
    batch_id = str(uuid4())
    frame = pd.DataFrame(items)
    try:
        _apply_inventory_groups(
            supabase, frame, batch_id, operated_by, today, container_key
        )
        container_values = {"status": STATE_POSTED}
        if auto_arrival:
            container_values.update({
                "actual_arrival_date": today.isoformat(),
                "actual_arrival_at": None,
            })
        (
            supabase.table("inventory_container_imports")
            .update(container_values)
            .eq("container_key", container_key)
            .execute()
        )
        event_time = datetime.now(timezone.utc)
        events = []
        if auto_arrival:
            arrival_event = build_container_event(
                original, container_key, "到柜", STATE_IN_TRANSIT,
                STATE_ARRIVED, today, operated_by,
                "直接入库：系统自动确认到柜",
            )
            arrival_event["created_at"] = event_time.isoformat()
            events.append(arrival_event)
        posting_event = build_container_event(
            original, container_key, "入库", previous, STATE_POSTED,
            today, operated_by, f"{note}｜库存批次：{batch_id}".strip("｜"),
        )
        posting_event["created_at"] = (
            event_time + timedelta(microseconds=1)
        ).isoformat()
        events.append(posting_event)
        return (
            supabase.table("inventory_container_events")
            .insert(events)
            .execute()
            .data
        )
    except Exception:
        _rollback_posting(
            supabase, batch_id, container_key, original, operated_by
        )
        raise


def _apply_inventory_groups(
    supabase, frame, batch_id, operated_by, today, container_key
):
    for (department, category), group in frame.groupby(
        ["department", "category"], dropna=False
    ):
        adjustments = pd.DataFrame({
            "日期": today,
            "操作": "增加",
            "品牌": group["brand"].fillna(""),
            "材质": group["material"].fillna(""),
            "颜色": group["color"].fillna(""),
            "尺码": group["size"].fillna(""),
            "数量": pd.to_numeric(group["quantity"]).astype(int),
            "成本": pd.to_numeric(
                group["unit_cost"], errors="coerce"
            ),
            "备注": (
                "货柜入库："
                + str(group["container_no"].iloc[0] or container_key)
            ),
        })
        apply_adjustment_rows(
            supabase,
            str(department or ""),
            str(category or ""),
            adjustments,
            created_by=operated_by,
            source_type="bulk",
            batch_id=batch_id,
        )


def _load_container_rows(supabase, container_key):
    rows = (
        supabase.table("inventory_container_imports")
        .select(
            "container_no,status,department,category,brand,material,"
            "color,size,quantity,unit_cost,actual_arrival_date,actual_arrival_at"
        )
        .eq("container_key", container_key)
        .execute()
        .data
    )
    if not rows:
        raise ValueError("未找到货柜记录")
    states = {str(row.get("status") or "") for row in rows}
    if len(states) != 1:
        raise ValueError("同一货柜存在多个状态，请先检查数据")
    return rows


def _ensure_not_posted(supabase, container_key):
    events = (
        supabase.table("inventory_container_events")
        .select("id")
        .eq("container_key", container_key)
        .eq("event_type", "入库")
        .limit(1)
        .execute()
        .data
    )
    if events:
        raise ValueError("这个货柜已经入库，不能重复操作")


def _rollback_posting(
    supabase, batch_id, container_key, original, operated_by
):
    try:
        supabase.rpc(
            "reverse_inventory_movement_batch",
            {"p_batch_id": batch_id, "p_created_by": operated_by},
        ).execute()
    except Exception:
        pass
    finally:
        (
            supabase.table("inventory_container_imports")
            .update({
                "status": original["status"],
                "actual_arrival_date": original.get("actual_arrival_date"),
                "actual_arrival_at": original.get("actual_arrival_at"),
            })
            .eq("container_key", container_key)
            .execute()
        )
