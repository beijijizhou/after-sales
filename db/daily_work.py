"""Persistence for personal daily-work checklists."""

import pandas as pd


TASK_COLUMNS = (
    "id,owner_username,section,task_name,task_kind,sort_order,is_active,"
    "created_by,created_at,updated_at"
)
DAY_COLUMNS = (
    "id,owner_username,work_date,summary,blockers,next_plan,updated_by,"
    "created_at,updated_at"
)
RECORD_COLUMNS = (
    "id,day_id,task_id,task_name_snapshot,section_snapshot,task_kind_snapshot,"
    "status,note,updated_by,updated_at"
)


def load_tasks(supabase, owner_username, active_only=True):
    query = (
        supabase.table("personal_daily_work_tasks")
        .select(TASK_COLUMNS)
        .eq("owner_username", _text(owner_username))
        .order("sort_order")
    )
    if active_only:
        query = query.eq("is_active", True)
    return pd.DataFrame(query.execute().data or [])


def create_task(
    supabase, owner_username, section, task_name, task_kind, sort_order,
    created_by,
):
    payload = {
        "owner_username": _required(owner_username, "缺少任务归属账号"),
        "section": _required(section, "请填写工作分类"),
        "task_name": _required(task_name, "请填写工作事项"),
        "task_kind": _task_kind(task_kind),
        "sort_order": int(sort_order),
        "created_by": _required(created_by, "缺少操作人"),
        "updated_by": _required(created_by, "缺少操作人"),
    }
    return (
        supabase.table("personal_daily_work_tasks")
        .insert(payload).execute().data
    )


def set_task_active(supabase, task_ids, is_active, updated_by):
    ids = [str(value) for value in task_ids if str(value).strip()]
    if not ids:
        return []
    return (
        supabase.table("personal_daily_work_tasks")
        .update({
            "is_active": bool(is_active),
            "updated_by": _required(updated_by, "缺少操作人"),
        })
        .in_("id", ids).execute().data
    )


def load_daily_work(supabase, owner_username, work_date):
    days = (
        supabase.table("personal_daily_work_days")
        .select(DAY_COLUMNS)
        .eq("owner_username", _text(owner_username))
        .eq("work_date", work_date.isoformat())
        .limit(1).execute().data
    ) or []
    if not days:
        return {}, pd.DataFrame(columns=RECORD_COLUMNS.split(","))
    day = days[0]
    records = (
        supabase.table("personal_daily_work_records")
        .select(RECORD_COLUMNS).eq("day_id", day["id"])
        .execute().data
    ) or []
    return day, pd.DataFrame(records)


def save_daily_work(
    supabase, owner_username, work_date, summary, blockers, next_plan,
    records, updated_by,
):
    owner = _required(owner_username, "缺少记录归属账号")
    actor = _required(updated_by, "缺少操作人")
    day_payload = {
        "owner_username": owner,
        "work_date": work_date.isoformat(),
        "summary": _text(summary),
        "blockers": _text(blockers),
        "next_plan": _text(next_plan),
        "updated_by": actor,
    }
    saved_days = (
        supabase.table("personal_daily_work_days")
        .upsert(
            day_payload, on_conflict="owner_username,work_date"
        ).execute().data
    ) or []
    if not saved_days:
        raise RuntimeError("每日工作记录保存后未返回日期批次")
    day_id = saved_days[0]["id"]
    payload = []
    for record in records:
        payload.append({
            "day_id": day_id,
            "task_id": _required(record.get("task_id"), "任务标识缺失"),
            "task_name_snapshot": _required(
                record.get("task_name"), "工作事项缺失"
            ),
            "section_snapshot": _required(
                record.get("section"), "工作分类缺失"
            ),
            "task_kind_snapshot": _task_kind(record.get("task_kind")),
            "status": _status(record.get("status")),
            "note": _text(record.get("note")),
            "updated_by": actor,
        })
    if payload:
        (
            supabase.table("personal_daily_work_records")
            .upsert(payload, on_conflict="day_id,task_id")
            .execute()
        )
    return day_id


def load_daily_work_history(supabase, owner_username, start_date, end_date):
    days = (
        supabase.table("personal_daily_work_days")
        .select(DAY_COLUMNS)
        .eq("owner_username", _text(owner_username))
        .gte("work_date", start_date.isoformat())
        .lte("work_date", end_date.isoformat())
        .order("work_date", desc=True).execute().data
    ) or []
    if not days:
        return pd.DataFrame(), pd.DataFrame()
    day_ids = [row["id"] for row in days]
    records = (
        supabase.table("personal_daily_work_records")
        .select(RECORD_COLUMNS).in_("day_id", day_ids)
        .execute().data
    ) or []
    return pd.DataFrame(days), pd.DataFrame(records)


def _status(value):
    value = _text(value)
    if value not in {"pending", "completed", "not_applicable"}:
        raise ValueError("工作状态无效")
    return value


def _task_kind(value):
    value = _text(value)
    if value not in {"daily", "as_needed"}:
        raise ValueError("任务类型无效")
    return value


def _required(value, message):
    value = _text(value)
    if not value:
        raise ValueError(message)
    return value


def _text(value):
    return str(value or "").strip()
