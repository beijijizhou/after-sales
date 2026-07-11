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
    if st.button("刷新当前日期多件订单", use_container_width=True):
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
    rpc_summary_rows = load_person_platform_summary_rows(supabase, selected_date, user_column, snapshot_at)
    person_platform_summary = build_person_platform_summary_from_rpc(rpc_summary_rows)
    user_summary = summarize_by_user_from_rpc(rpc_summary_rows)
    hourly_summary = summarize_hourly_from_rpc(
        load_hourly_summary_rows(supabase, selected_date, user_column, snapshot_at),
        selected_date,
    )
    hourly_person_rows = load_hourly_person_client_rows(supabase, selected_date, user_column, snapshot_at)
    person_switch_df = build_person_switch_table(hourly_person_rows)
    if person_platform_summary.empty:
        raise ValueError("empty database summary")
    if user_summary.empty:
        raise ValueError("empty user summary")
    return user_summary, person_platform_summary, hourly_summary, person_switch_df


def load_legacy_summary(supabase, selected_date, title, user_column, snapshot_at):
    raw_df = load_daily_production_rows(supabase, selected_date, user_column, snapshot_at)
    if raw_df.empty:
        st.warning(f"{selected_date.isoformat()} 没有生产数据")
        st.stop()

    df = prepare_production_df(raw_df, user_column)
    if df.empty:
        st.warning(f"{selected_date.isoformat()} 没有{title}人员数据")
        st.stop()

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
    except Exception:
        st.warning("生产统计正在使用旧算法。请在 Supabase SQL Editor 运行最新版 sql/production_summary_functions.sql")
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
        st.caption(f"统计截止时间：{snapshot_at.strftime('%Y-%m-%d %H:%M:%S')} NY")

    try:
        user_summary, person_platform_summary, hourly_summary, person_switch_df, working_hours = (
            resolve_production_summary(supabase, selected_date, title, user_column, snapshot_at)
        )
        render_kpis(user_summary, working_hours)
        render_person_platform_table(person_platform_summary, title)
        render_hourly_production(hourly_summary)
        render_person_switch_table(person_switch_df)
    except Exception as e:
        st.error(f"数据加载失败：{e}")
