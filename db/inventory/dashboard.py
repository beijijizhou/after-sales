from datetime import timedelta

import pandas as pd

from db.consumables import (
    load_consumable_batches,
    load_departments,
)
from db.inventory.core.pagination import fetch_range_pages
from db.inventory.dashboard_overview import load_inventory_overview
from db.inventory.dashboard_completion import (
    DAILY_COMPLETION_START_DATE,
    DAILY_FLOW_LABELS,
    active_consumable_issue_dates as _active_consumable_issue_dates,
    active_inventory_movements as _active_inventory_movements,
    active_daily_outbound_ack_dates,
    build_automatic_missing_dates,
    build_daily_completion_dates,
    build_daily_completion_table,
    build_today_completion_status,
    build_today_completion_table,
)
from db.inventory.operations.daily_outbound_versions import (
    load_daily_outbound_revisions,
)


def load_daily_completion_summary(supabase, today, lookback_days=7):
    summary, _completed, _start_date = load_daily_completion_status(
        supabase, today, lookback_days
    )
    return summary


def load_daily_completion_status(
    supabase, today, lookback_days=None,
    start_date=DAILY_COMPLETION_START_DATE,
):
    if lookback_days is not None:
        rolling_start = today - timedelta(days=lookback_days - 1)
        start_date = max(start_date, rolling_start)
    start_date = min(start_date, today)
    movements = _load_daily_inventory_movements(
        supabase, start_date, today
    )
    departments = load_departments(supabase)
    dtf_rows = departments[departments["code"].eq("DTF")]
    department_id = dtf_rows.iloc[0]["id"] if not dtf_rows.empty else None
    consumable_batches = (
        load_consumable_batches(
            supabase, department_id=department_id,
            start_date=start_date, end_date=today, limit=5000,
        )
        if department_id else pd.DataFrame()
    )
    completed = build_daily_completion_dates(
        movements, consumable_batches
    )
    acknowledgements = load_daily_outbound_revisions(
        supabase, "DTF", "黑白短袖", start_date, today
    )
    completed["black_white"].update(
        active_daily_outbound_ack_dates(acknowledgements)
    )
    history_end = today - timedelta(days=1)
    return (
        build_daily_completion_table(completed, start_date, history_end),
        completed,
        start_date,
    )


def build_daily_operation_table(summary, completed, today):
    if summary.empty:
        return pd.DataFrame(columns=[
            "出库项目", "数据方式", "截止昨日", "待补日期",
            "今日状态", "当前操作",
        ])
    result = summary.copy()
    today_status = build_today_completion_table(
        completed, today
    ).set_index("出库项目")
    result["截止昨日"] = result.apply(
        lambda row: f"{int(row['已完成天数'])}/{int(row['检查天数'])} 天",
        axis=1,
    )
    result["今日状态"] = result["出库项目"].map(
        today_status["今日状态"]
    )
    result["当前操作"] = result.apply(
        _daily_operation_label, axis=1
    )
    return result.rename(columns={"待处理日期": "待补日期"})[[
        "出库项目", "数据方式", "截止昨日", "待补日期",
        "今日状态", "当前操作",
    ]]


def _daily_operation_label(row):
    missing = int(row["待处理天数"])
    if missing:
        if row["数据方式"] == "系统读取":
            return f"系统预览并补扣 {missing} 天"
        return f"补录实际出库 {missing} 天"
    return "无需补录"


def _load_daily_inventory_movements(supabase, start_date, end_date):
    columns = (
        "department,category,movement_date,quantity_change,reason,"
        "batch_id,reversal_of_batch_id,created_at"
    )

    def fetch_page(start, end):
        return (
            supabase.table("inventory_movements")
            .select(columns)
            .gte("movement_date", start_date.isoformat())
            .lte("movement_date", end_date.isoformat())
            .order("movement_date")
            .order("created_at")
            .range(start, end)
            .execute().data
            or []
        )

    rows = fetch_range_pages(fetch_page, limit=None)
    return pd.DataFrame(rows)
