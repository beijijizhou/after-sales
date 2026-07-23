import pandas as pd
import streamlit as st

from ui.production.components import (
    render_hourly_production,
    render_person_switch_table,
)
from utils.production import (
    build_person_switch_table,
    load_hourly_person_client_rows,
    summarize_hourly_from_rpc,
)
from utils.production.constants import HALOO_PLATFORM, OTHER_CLIENT


def render_daily_workflow(supabase, state, user_column, snapshot_at=None):
    if state.platforms and any(
        platform != HALOO_PLATFORM for platform in state.platforms
    ):
        st.info(
            "单日工作流目前按 Haloo / 小平台统计，"
            "不支持进一步按具体小平台拆分。"
        )
        return

    dates = pd.date_range(
        state.start_date, state.end_date, freq="D"
    ).date.tolist()
    work_date = st.selectbox(
        "工作流日期",
        dates,
        index=len(dates) - 1,
        format_func=lambda value: value.isoformat(),
        key=f"qa_workflow_date_{state.end_date}",
    )
    effective_snapshot = (
        snapshot_at if snapshot_at and work_date == snapshot_at.date()
        else None
    )
    try:
        rows = load_hourly_person_client_rows(
            supabase, work_date, user_column, effective_snapshot
        )
    except Exception as error:
        st.warning(f"单日工作流加载失败：{error}")
        return
    rows = filter_workflow_rows(rows, state)
    if rows.empty:
        st.info("该日期在当前筛选条件下没有工作流数据")
        return

    hourly_rows = rows.groupby(
        "hour_start_at", as_index=False
    ).agg(
        scan_count=("total_count", "sum"),
        haloo_count=("haloo_count", "sum"),
    )
    hourly = summarize_hourly_from_rpc(hourly_rows, work_date)
    render_hourly_production(hourly)
    render_person_switch_table(build_person_switch_table(rows))


def filter_workflow_rows(rows, state):
    if rows.empty:
        return rows
    result = rows.copy()
    if state.people:
        result = result[result["person"].isin(state.people)]
    count_columns = ["haloo_count", "other_count", "total_count"]
    for column in count_columns:
        result[column] = pd.to_numeric(
            result[column], errors="coerce"
        ).fillna(0).astype(int)
    haloo_only = (
        state.client_type == HALOO_PLATFORM
        or state.platforms == (HALOO_PLATFORM,)
    )
    if haloo_only:
        result["other_count"] = 0
        result["total_count"] = result["haloo_count"]
    elif state.client_type == OTHER_CLIENT:
        result["haloo_count"] = 0
        result["total_count"] = result["other_count"]
    return result[result["total_count"] > 0].reset_index(drop=True)
