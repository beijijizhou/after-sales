"""Pure display models for personal daily work."""

import pandas as pd


STATUS_LABELS = {
    "pending": "待处理",
    "completed": "已完成",
    "not_applicable": "不适用",
}
STATUS_CODES = {label: code for code, label in STATUS_LABELS.items()}
TASK_KIND_LABELS = {"daily": "每日必做", "as_needed": "按需处理"}


def build_daily_editor(tasks, records):
    saved = {
        str(row.get("task_id")): row
        for row in _records(records)
    }
    rows = []
    for task in _records(tasks):
        task_id = str(task.get("id") or "")
        record = saved.get(task_id, {})
        default = "pending" if task.get("task_kind") == "daily" else "not_applicable"
        rows.append({
            "_task_id": task_id,
            "_task_kind": str(task.get("task_kind") or "daily"),
            "类别": str(task.get("section") or ""),
            "类型": TASK_KIND_LABELS.get(task.get("task_kind"), "每日必做"),
            "工作事项": str(task.get("task_name") or ""),
            "状态": STATUS_LABELS.get(record.get("status", default), "待处理"),
            "备注": str(record.get("note") or ""),
        })
    return pd.DataFrame(rows)


def editor_records(edited):
    result = []
    for row in _records(edited):
        status = STATUS_CODES.get(str(row.get("状态") or ""))
        if not status:
            raise ValueError("请选择有效的工作状态")
        result.append({
            "task_id": row.get("_task_id"),
            "task_kind": row.get("_task_kind"),
            "section": row.get("类别"),
            "task_name": row.get("工作事项"),
            "status": status,
            "note": row.get("备注"),
        })
    return result


def completion_summary(editor):
    frame = pd.DataFrame(editor)
    if frame.empty:
        return {"total": 0, "completed": 0, "pending": 0, "not_applicable": 0, "rate": 0}
    counts = frame["状态"].value_counts()
    completed = int(counts.get("已完成", 0))
    pending = int(counts.get("待处理", 0))
    not_applicable = int(counts.get("不适用", 0))
    applicable = completed + pending
    return {
        "total": len(frame),
        "completed": completed,
        "pending": pending,
        "not_applicable": not_applicable,
        "rate": round(completed * 100 / applicable) if applicable else 100,
    }


def history_summary(days, records):
    days = pd.DataFrame(days).copy()
    records = pd.DataFrame(records).copy()
    if days.empty:
        return pd.DataFrame(columns=["日期", "已完成", "待处理", "不适用", "完成率", "当日总结"])
    counts = pd.DataFrame(columns=["day_id", "status", "count"])
    if not records.empty:
        counts = records.groupby(["day_id", "status"]).size().rename("count").reset_index()
    rows = []
    for day in days.to_dict("records"):
        current = counts[counts["day_id"].astype(str) == str(day["id"])]
        values = dict(zip(current["status"], current["count"]))
        completed = int(values.get("completed", 0))
        pending = int(values.get("pending", 0))
        not_applicable = int(values.get("not_applicable", 0))
        applicable = completed + pending
        rows.append({
            "日期": day.get("work_date"),
            "已完成": completed,
            "待处理": pending,
            "不适用": not_applicable,
            "完成率": round(completed * 100 / applicable) if applicable else 100,
            "当日总结": day.get("summary") or "",
        })
    return pd.DataFrame(rows)


def history_detail(day_id, records):
    frame = pd.DataFrame(records).copy()
    if frame.empty:
        return pd.DataFrame(columns=["类别", "类型", "工作事项", "状态", "备注"])
    frame = frame[frame["day_id"].astype(str) == str(day_id)]
    return pd.DataFrame({
        "类别": frame["section_snapshot"],
        "类型": frame["task_kind_snapshot"].map(TASK_KIND_LABELS),
        "工作事项": frame["task_name_snapshot"],
        "状态": frame["status"].map(STATUS_LABELS),
        "备注": frame["note"].fillna(""),
    })


def _records(value):
    if isinstance(value, pd.DataFrame):
        return value.to_dict("records")
    return list(value or [])
