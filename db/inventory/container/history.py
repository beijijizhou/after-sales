import pandas as pd


def load_container_events(supabase, container_key=None):
    query = supabase.table("inventory_container_events").select(
        "container_key,container_no,event_type,effective_date,previous_status,"
        "new_status,operated_by,note,created_at"
    )
    if container_key:
        query = query.eq("container_key", container_key)
    response = (
        query.order("effective_date", desc=True)
        .order("created_at", desc=True)
        .execute()
    )
    return pd.DataFrame(response.data)


def update_container_status(
    supabase, container_key, new_status, effective_date, operated_by, note=""
):
    current = (
        supabase.table("inventory_container_imports")
        .select("container_no,status")
        .eq("container_key", container_key)
        .limit(1)
        .execute()
    )
    if not current.data:
        raise ValueError("未找到货柜记录")

    previous_status = current.data[0].get("status")
    container_no = current.data[0].get("container_no")
    actual_date = effective_date.isoformat() if new_status == "已到货" else None
    (
        supabase.table("inventory_container_imports")
        .update({
            "status": new_status,
            "actual_arrival_date": actual_date,
        })
        .eq("container_key", container_key)
        .execute()
    )
    event_type = "到货" if new_status == "已到货" else "状态变更"
    event = {
        "container_key": container_key,
        "container_no": container_no,
        "event_type": event_type,
        "effective_date": effective_date.isoformat(),
        "previous_status": previous_status,
        "new_status": new_status,
        "operated_by": operated_by,
        "note": note.strip() or None,
    }
    return supabase.table("inventory_container_events").insert(event).execute().data


def build_container_history_display(df):
    columns = [
        "事件日期", "记录时间（纽约）", "货柜号", "事件", "原状态",
        "新状态", "操作人", "备注",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)
    display = df.copy()
    display["effective_date"] = pd.to_datetime(
        display["effective_date"], errors="coerce"
    ).dt.date
    created = pd.to_datetime(display["created_at"], errors="coerce", utc=True)
    display["created_at"] = created.dt.tz_convert("America/New_York").dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    display = display.rename(columns={
        "effective_date": "事件日期", "created_at": "记录时间（纽约）",
        "container_no": "货柜号", "event_type": "事件",
        "previous_status": "原状态", "new_status": "新状态",
        "operated_by": "操作人", "note": "备注",
    })
    return display.reindex(columns=columns).fillna("")
