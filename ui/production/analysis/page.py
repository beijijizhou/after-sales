import streamlit as st

from ui.production.components import render_person_platform_table
from ui.production.analysis.filters import (
    render_period_date_filter,
    render_period_filters,
)
from ui.production.analysis.productivity import (
    render_productivity_chart,
)
from ui.production.analysis.views import (
    render_client_summary,
    render_daily_summary,
    render_platform_summary,
    render_summary_metrics,
)
from utils.date_display import format_date_with_weekday
from utils.production import load_period_person_platform_rows
from utils.production.period_summary import (
    build_daily_summary,
    build_period_person_platform_summary,
    build_platform_summary,
    get_period_dates,
    prepare_period_rows,
)


def render_qa_period_analysis(
    supabase, selected_date, user_column, snapshot_at=None
):
    start_date, end_date = get_period_dates(selected_date)
    st.subheader("质检总结分析")
    start_date, end_date = render_period_date_filter(
        start_date, end_date
    )
    st.caption(
        f"当前统计范围：{format_date_with_weekday(start_date)} 至 "
        f"{format_date_with_weekday(end_date)}（纽约时间）"
    )

    try:
        rpc_rows = load_period_person_platform_rows(
            supabase, start_date, end_date, user_column, snapshot_at
        )
    except Exception as error:
        st.warning("质检区间汇总函数尚未更新")
        st.caption(
            "请在 Supabase SQL Editor 运行 "
            "sql/qa_period_summary_functions.sql"
        )
        st.caption(str(error))
        return

    rows = prepare_period_rows(rpc_rows)
    if rows.empty:
        st.info("当前日期范围没有质检数据")
        return

    filtered, filter_state = render_period_filters(
        rows, start_date, end_date
    )
    if filtered.empty:
        st.info("当前筛选条件没有质检数据")
        return

    daily = build_daily_summary(
        filtered, filter_state.start_date, filter_state.end_date
    )
    render_summary_metrics(filtered, daily)
    people_tab, daily_tab, platform_tab, client_tab, rate_tab = st.tabs([
        "人员分析", "每日汇总", "平台分析",
        "Haloo / 小平台", "时产分析",
    ])
    with people_tab:
        render_person_platform_table(
            build_period_person_platform_summary(filtered), "质检"
        )
    with daily_tab:
        render_daily_summary(daily)
    with platform_tab:
        render_platform_summary(build_platform_summary(filtered))
    with client_tab:
        render_client_summary(daily)
    with rate_tab:
        render_productivity_chart(daily, filtered)
