from db.inventory.container.workflow.state import (
    STATE_ARRIVED,
    build_container_event,
    validate_container_transition,
)


def confirm_container_arrival_date(
    supabase, container_key, arrival_date, operated_by, note=""
):
    current = _load_current_container(supabase, container_key)
    previous = validate_container_transition(
        current["status"], STATE_ARRIVED
    )
    try:
        (
            supabase.table("inventory_container_imports")
            .update({
                "expected_arrival_date": arrival_date.isoformat(),
                "actual_arrival_date": arrival_date.isoformat(),
                "actual_arrival_at": None,
                "status": STATE_ARRIVED,
            })
            .eq("container_key", container_key)
            .execute()
        )
        event = build_container_event(
            current, container_key, "到柜", previous, STATE_ARRIVED,
            arrival_date, operated_by, note,
        )
        return (
            supabase.table("inventory_container_events")
            .insert(event)
            .execute()
            .data
        )
    except Exception:
        (
            supabase.table("inventory_container_imports")
            .update({
                "expected_arrival_date": current.get(
                    "expected_arrival_date"
                ),
                "actual_arrival_date": current.get("actual_arrival_date"),
                "actual_arrival_at": current.get("actual_arrival_at"),
                "status": current["status"],
            })
            .eq("container_key", container_key)
            .execute()
        )
        raise


def confirm_container_arrival(
    supabase, container_key, arrival_at, operated_by, note=""
):
    current = _load_current_container(supabase, container_key)
    previous = validate_container_transition(
        current["status"], STATE_ARRIVED
    )
    try:
        (
            supabase.table("inventory_container_imports")
            .update({
                "status": STATE_ARRIVED,
                "actual_arrival_date": arrival_at.date().isoformat(),
                "actual_arrival_at": arrival_at.isoformat(),
            })
            .eq("container_key", container_key)
            .execute()
        )
        event = build_container_event(
            current, container_key, "到柜", previous, STATE_ARRIVED,
            arrival_at.date(), operated_by, note, arrival_at,
        )
        return (
            supabase.table("inventory_container_events")
            .insert(event)
            .execute()
            .data
        )
    except Exception:
        (
            supabase.table("inventory_container_imports")
            .update({
                "status": current["status"],
                "actual_arrival_date": None,
                "actual_arrival_at": None,
            })
            .eq("container_key", container_key)
            .execute()
        )
        raise


def _load_current_container(supabase, container_key):
    rows = (
        supabase.table("inventory_container_imports")
        .select(
            "container_no,status,expected_arrival_date,"
            "actual_arrival_date,actual_arrival_at"
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
    return rows[0]
