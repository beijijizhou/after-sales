import re
from datetime import datetime
from zoneinfo import ZoneInfo

from db.inventory.container.workflow.state import (
    STATE_ARRIVED,
    STATE_IN_TRANSIT,
    STATE_POSTED,
    build_container_event,
    normalize_container_state,
)


NY_TIMEZONE = ZoneInfo("America/New_York")
BATCH_PATTERN = re.compile(
    r"库存批次[：:]\s*([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})"
)


def get_container_undo_kind(status):
    current = str(status or "").strip()
    if current == STATE_POSTED:
        return "posting"
    if current == STATE_ARRIVED:
        return "arrival"
    return None


def undo_latest_container_confirmation(
    supabase, container_key, operated_by, note="",
):
    current = _load_current_container(supabase, container_key)
    kind = get_container_undo_kind(current["status"])
    if kind == "posting":
        return _undo_posting(
            supabase, container_key, current, operated_by, note
        )
    if kind == "arrival":
        return _undo_arrival(
            supabase, container_key, current, operated_by, note
        )
    raise ValueError("当前货柜没有可撤销的到柜或入库确认")


def _undo_posting(supabase, container_key, current, operated_by, note):
    event = _load_latest_event(supabase, container_key, "入库")
    batch_id = _extract_inventory_batch_id(event.get("note"))
    if not batch_id:
        raise ValueError("这次入库没有关联库存批次，无法安全撤销")
    previous = event.get("previous_status") or STATE_ARRIVED
    if normalize_container_state(previous) != STATE_ARRIVED:
        raise ValueError("入库记录的上一步状态异常，请先核对操作历史")

    _update_container(supabase, container_key, {"status": previous})
    try:
        supabase.rpc(
            "reverse_inventory_movement_batch",
            {"p_batch_id": batch_id, "p_created_by": operated_by},
        ).execute()
    except Exception:
        _update_container(
            supabase, container_key, {"status": current["status"]}
        )
        raise

    undo_note = _undo_note(
        note, f"已反向撤销库存批次：{batch_id}"
    )
    undo_event = build_container_event(
        current,
        container_key,
        "撤销入库",
        current["status"],
        previous,
        datetime.now(NY_TIMEZONE).date(),
        operated_by,
        undo_note,
        _parse_arrival_at(current.get("actual_arrival_at")),
    )
    _insert_event(supabase, undo_event)
    return {"kind": "posting", "status": previous, "batch_id": batch_id}


def _undo_arrival(supabase, container_key, current, operated_by, note):
    event = _load_latest_event(supabase, container_key, "到柜")
    previous = event.get("previous_status") or STATE_IN_TRANSIT
    if normalize_container_state(previous) != STATE_IN_TRANSIT:
        raise ValueError("到柜记录的上一步状态异常，请先核对操作历史")
    values = {
        "status": previous,
        "actual_arrival_date": None,
        "actual_arrival_at": None,
    }
    _update_container(supabase, container_key, values)
    undo_event = build_container_event(
        current,
        container_key,
        "撤销到柜",
        current["status"],
        previous,
        datetime.now(NY_TIMEZONE).date(),
        operated_by,
        _undo_note(note, "已清除实际到柜日期和时间"),
    )
    try:
        _insert_event(supabase, undo_event)
    except Exception:
        _update_container(supabase, container_key, {
            "status": current["status"],
            "actual_arrival_date": current.get("actual_arrival_date"),
            "actual_arrival_at": current.get("actual_arrival_at"),
        })
        raise
    return {"kind": "arrival", "status": previous, "batch_id": None}


def _load_current_container(supabase, container_key):
    rows = (
        supabase.table("inventory_container_imports")
        .select(
            "container_no,status,actual_arrival_date,actual_arrival_at"
        )
        .eq("container_key", container_key)
        .execute()
        .data
        or []
    )
    if not rows:
        raise ValueError("未找到货柜记录")
    states = {str(row.get("status") or "") for row in rows}
    if len(states) != 1:
        raise ValueError("同一货柜存在多个状态，请先检查数据")
    return rows[0]


def _load_latest_event(supabase, container_key, event_type):
    rows = (
        supabase.table("inventory_container_events")
        .select(
            "id,container_no,event_type,previous_status,new_status,note,"
            "actual_arrival_at,created_at"
        )
        .eq("container_key", container_key)
        .eq("event_type", event_type)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise ValueError(f"没有找到可撤销的{event_type}记录")
    return rows[0]


def _extract_inventory_batch_id(note):
    match = BATCH_PATTERN.search(str(note or ""))
    return match.group(1) if match else None


def _update_container(supabase, container_key, values):
    return (
        supabase.table("inventory_container_imports")
        .update(values)
        .eq("container_key", container_key)
        .execute()
        .data
    )


def _insert_event(supabase, event):
    return (
        supabase.table("inventory_container_events")
        .insert(event)
        .execute()
        .data
    )


def _parse_arrival_at(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _undo_note(user_note, system_note):
    return "｜".join(
        value for value in [str(user_note or "").strip(), system_note]
        if value
    )
