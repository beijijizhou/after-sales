STATE_IN_TRANSIT = "在途"
STATE_ARRIVED = "已到柜"
STATE_POSTED = "已入库"
STATE_CANCELLED = "取消"

LEGACY_STATE_MAP = {
    "未到货": STATE_IN_TRANSIT,
    "延迟": STATE_IN_TRANSIT,
    "已到货": STATE_ARRIVED,
}

ALLOWED_TRANSITIONS = {
    STATE_IN_TRANSIT: {STATE_ARRIVED, STATE_POSTED, STATE_CANCELLED},
    STATE_ARRIVED: {STATE_POSTED},
    STATE_POSTED: set(),
    STATE_CANCELLED: set(),
}


def normalize_container_state(value):
    state = str(value or "").strip()
    return LEGACY_STATE_MAP.get(state, state)


def validate_container_transition(current, target):
    normalized_current = normalize_container_state(current)
    if target not in ALLOWED_TRANSITIONS.get(normalized_current, set()):
        raise ValueError(
            f"货柜状态不能从“{normalized_current}”变更为“{target}”"
        )
    return normalized_current


def build_container_event(
    row, container_key, event_type, previous, target,
    effective_date, operated_by, note="", arrival_at=None,
):
    return {
        "container_key": container_key,
        "container_no": row.get("container_no"),
        "event_type": event_type,
        "effective_date": effective_date.isoformat(),
        "actual_arrival_at": arrival_at.isoformat() if arrival_at else None,
        "previous_status": previous,
        "new_status": target,
        "operated_by": operated_by,
        "note": note.strip() or None,
    }
