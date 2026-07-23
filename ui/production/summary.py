from datetime import datetime

import pandas as pd
import streamlit as st

from ui.production.components import (
    get_working_hours_from_user_summary,
    render_hourly_production,
    render_kpis,
    render_person_platform_table,
    render_person_switch_table,
)
from ui.production.analysis import render_qa_period_analysis
from utils.date_display import format_date_with_weekday
from utils.multiple_count_helpers import refresh_multiple_counts
from utils.production_helpers import (
    NY_TIMEZONE,
    build_person_platform_summary,
    build_person_platform_summary_from_rpc,
    build_person_switch_table,
    get_working_hours,
    load_daily_production_rows,
    load_hourly_person_client_rows,
    load_hourly_summary_rows,
    load_person_platform_summary_rows,
    prepare_production_df,
    summarize_by_hour,
    summarize_by_user,
    summarize_by_user_from_rpc,
    summarize_hourly_from_rpc,
)


def render_refresh_multiple_counts_button(supabase, selected_date):
    if st.button("刷新当前日期多件订单", width="stretch"):
        try:
            with st.spinner(f"正在刷新 {selected_date.isoformat()} 多件订单..."):
                refresh_multiple_counts(supabase, selected_date)
            st.success("多件订单已刷新")
            st.rerun()
        except Exception as e:
            st.error(f"多件订单刷新失败：{e}")
            if "statement timeout" in str(e):
                st.info("数据库刷新超时。请在 Supabase SQL Editor 重新运行最新版 sql/refresh_barcode_multiple_counts.sql 后再试。")
            else:
                st.info("请先在 Supabase SQL Editor 运行 sql/refresh_barcode_multiple_counts.sql")


def load_rpc_summary(supabase, selected_date, user_column, snapshot_at):
    rpc_summary_rows = load_person_platform_summary_rows(
        supabase, selected_date, user_column, snapshot_at
    )
    if rpc_summary_rows.empty:
        raise ValueError("人员平台汇总 RPC 返回空数据")

    person_platform_summary = build_person_platform_summary_from_rpc(rpc_summary_rows)
    if person_platform_summary.empty:
        raise ValueError(f"人员平台汇总字段不匹配：{list(rpc_summary_rows.columns)}")

    user_summary = summarize_by_user_from_rpc(rpc_summary_rows)
    if user_summary.empty:
        raise ValueError(f"人员汇总字段不匹配：{list(rpc_summary_rows.columns)}")

    hourly_rows = load_hourly_summary_rows(supabase, selected_date, user_column, snapshot_at)
    hourly_summary = summarize_hourly_from_rpc(hourly_rows, selected_date)
    hourly_person_rows = load_hourly_person_client_rows(
        supabase, selected_date, user_column, snapshot_at
    )
    person_switch_df = build_person_switch_table(hourly_person_rows)
    return user_summary, person_platform_summary, hourly_summary, person_switch_df


def load_legacy_summary(supabase, selected_date, title, user_column, snapshot_at):
    raw_df = load_daily_production_rows(supabase, selected_date, user_column, snapshot_at)
    if raw_df.empty:
        raise ValueError(f"{selected_date.isoformat()} 没有生产数据")

    df = prepare_production_df(raw_df, user_column)
    if df.empty:
        raise ValueError(f"{selected_date.isoformat()} 没有{title}人员数据")

    return (
        summarize_by_user(df, user_column),
        build_person_platform_summary(df, user_column),
        summarize_by_hour(df, selected_date),
        pd.DataFrame(),
        get_working_hours(df),
    )


def resolve_production_summary(supabase, selected_date, title, user_column, snapshot_at):
    try:
        user_summary, person_platform_summary, hourly_summary, person_switch_df = load_rpc_summary(
            supabase, selected_date, user_column, snapshot_at
        )
    except Exception as e:
        if "RPC 返回空数据" in str(e):
            return load_legacy_summary(supabase, selected_date, title, user_column, snapshot_at)
        st.warning("数据库汇总函数暂时不可用，当前使用明细数据计算。")
        st.caption(f"RPC 详情：{e}")
        return load_legacy_summary(supabase, selected_date, title, user_column, snapshot_at)

    working_hours = get_working_hours_from_user_summary(user_summary)
    if hourly_summary.empty:
        st.warning("每小时产量正在使用旧算法。请在 Supabase SQL Editor 运行最新版 sql/production_summary_functions.sql")
        raw_df = load_daily_production_rows(supabase, selected_date, user_column, snapshot_at)
        df = prepare_production_df(raw_df, user_column)
        hourly_summary = summarize_by_hour(df, selected_date)
        person_switch_df = pd.DataFrame()
    return user_summary, person_platform_summary, hourly_summary, person_switch_df, working_hours


def render_production_summary(supabase, selected_date, title, user_column):
    st.title(title)
    render_refresh_multiple_counts_button(supabase, selected_date)
    snapshot_at = None
    if selected_date == datetime.now(NY_TIMEZONE).date():
        snapshot_at = datetime.now(NY_TIMEZONE)
        st.caption(
            "统计截止时间："
            f"{format_date_with_weekday(snapshot_at)} "
            f"{snapshot_at.strftime('%H:%M:%S')} NY"
        )

    if user_column == "scanned_by":
        daily_tab, analysis_tab = st.tabs([
            "当日工作流", "总结分析",
        ])
        with daily_tab:
            st.caption(
                f"当日统计：{format_date_with_weekday(selected_date)}"
                "（纽约时间）"
            )
            render_daily_production_content(
                supabase, selected_date, title,
                user_column, snapshot_at,
            )
        with analysis_tab:
            try:
                render_qa_period_analysis(
                    supabase, selected_date, user_column, snapshot_at
                )
            except Exception as e:
                st.error(f"数据加载失败：{e}")
        return

    render_daily_production_content(
        supabase, selected_date, title, user_column, snapshot_at
    )


def render_daily_production_content(
    supabase, selected_date, title, user_column, snapshot_at
):
    try:
        user_summary, person_platform_summary, hourly_summary, person_switch_df, working_hours = (
            resolve_production_summary(supabase, selected_date, title, user_column, snapshot_at)
        )
        render_kpis(user_summary, working_hours)
        render_person_platform_table(person_platform_summary, title)
        render_hourly_production(hourly_summary)
        render_person_switch_table(person_switch_df)
    except Exception as e:
        if "没有生产数据" in str(e) or "没有" + title in str(e):
            st.warning(str(e))
        else:
            st.error(f"数据加载失败：{e}")
