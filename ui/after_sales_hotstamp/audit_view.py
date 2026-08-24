"""Database-backed analysis of Google Sheets manual registrations."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.after_sales_hotstamp import (
    load_hotstamp_film_batch_rows,
    load_hotstamp_film_batches,
    load_hotstamp_manual_analysis,
)
from ui.after_sales_hotstamp.models import (
    build_daily_manual_summary,
    build_person_manual_summary,
    build_platform_person_summary,
    build_weekly_manual_summary,
    prepare_manual_analysis,
)


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_audit_view(supabase):
    st.subheader("Google Sheets 人工登记分析")
    try:
        batches = load_hotstamp_film_batches(supabase, limit=200)
    except Exception as exc:
        _render_migration_error(exc)
        return
    completed = batches[batches["status"] == "completed"] if not batches.empty else batches
    if completed.empty:
        st.info("数据库尚未导入 Google Sheets 人工登记数据。")
        return

    earliest = pd.to_datetime(completed["start_date"]).dt.date.min()
    latest = pd.to_datetime(completed["end_date"]).dt.date.max()
    today = datetime.now(NY_TIMEZONE).date()
    selected_range = st.date_input(
        "分析日期",
        value=(earliest, min(latest, today)),
        min_value=earliest,
        max_value=max(latest, today),
        key="manual_registration_analysis_range",
    )
    if not isinstance(selected_range, (tuple, list)) or len(selected_range) != 2:
        st.info("请选择开始和结束日期。")
        return
    start_date, end_date = selected_range
    try:
        rows = prepare_manual_analysis(
            load_hotstamp_manual_analysis(supabase, start_date, end_date)
        )
    except Exception as exc:
        _render_migration_error(exc)
        return
    if rows.empty:
        st.info("所选日期没有人工登记数据。")
        return

    platform = st.selectbox(
        "平台",
        ["全部平台", *sorted(rows["platform"].unique())],
        key="manual_registration_platform",
    )
    filtered = rows if platform == "全部平台" else rows[rows["platform"] == platform]
    _render_metrics(filtered)
    _render_source_rule()

    weekly_tab, platform_tab, person_tab, daily_tab = st.tabs([
        "周汇总", "平台与人员", "人员专项占比", "每日趋势",
    ])
    with weekly_tab:
        _render_weekly(build_weekly_manual_summary(filtered))
    with platform_tab:
        _render_platform_people(build_platform_person_summary(filtered))
    with person_tab:
        _render_people(build_person_manual_summary(filtered))
    with daily_tab:
        _render_daily(build_daily_manual_summary(filtered))


def render_batch_history(supabase):
    st.subheader("同步批次与原始登记")
    try:
        batches = load_hotstamp_film_batches(supabase, limit=200)
    except Exception as exc:
        st.error(f"同步批次加载失败：{exc}")
        return
    if batches.empty:
        st.info("尚未导入任何 Google 周表。")
        return
    display = batches.rename(columns={
        "source_file_name": "周表", "start_date": "开始日期",
        "end_date": "结束日期", "row_count": "有效登记行",
        "total_film_quantity": "膜总数", "invalid_row_count": "异常行",
        "operator": "操作人", "created_at": "同步时间", "status": "状态",
    })
    st.dataframe(
        display[[
            "周表", "开始日期", "结束日期", "有效登记行", "膜总数",
            "异常行", "操作人", "同步时间", "状态",
        ]],
        hide_index=True,
        width="stretch",
    )
    labels = {
        row.id: f"{row.source_file_name}｜{row.created_at}"
        for row in batches.itertuples(index=False)
    }
    selected = st.selectbox(
        "选择批次查看完整原始登记",
        list(labels),
        format_func=labels.get,
        key="hotstamp_film_batch_detail",
    )
    rows = load_hotstamp_film_batch_rows(supabase, selected)
    st.dataframe(rows, hide_index=True, width="stretch")


def _render_metrics(rows):
    registrations = int(rows["registration_count"].sum())
    film = int(rows["film_quantity"].sum())
    hoodie = int(rows["hoodie_registration_count"].sum())
    multi_press = int(rows["multi_press_registration_count"].sum())
    columns = st.columns(6)
    columns[0].metric("登记单数", f"{registrations:,}")
    columns[1].metric("登记膜数", f"{film:,}")
    columns[2].metric("平台数", rows["platform"].nunique())
    columns[3].metric("烫印人数", rows["hotstamp_person"].nunique())
    columns[4].metric("卫衣占比", f"{_percent(hoodie, registrations):.1f}%")
    columns[5].metric("多烫占比", f"{_percent(multi_press, registrations):.1f}%")


def _render_source_rule():
    with st.expander("数据口径"):
        st.markdown(
            "- 所有分析只使用已存入数据库的 Google Sheets 人工登记。\n"
            "- 登记单数是有效人工登记行数；膜数是登记的“数量”合计。\n"
            "- 卫衣、多烫和白板按原表字段汇总；汉森按平台字段统计。\n"
            "- 原表没有独立的“多件”字段，因此不推测多件数据。\n"
            "- 该页面不使用系统条码扫描数据，不判断均匀度。"
        )


def _render_weekly(rows):
    display = rows.rename(columns={
        "week_start": "周开始", "platform": "平台",
        "registration_count": "登记单数", "registration_share_percent": "周登记占比%",
        "film_quantity": "膜数", "film_share_percent": "周膜数占比%",
        "hoodie_registration_count": "卫衣登记", "hoodie_ratio_percent": "卫衣占比%",
        "multi_press_registration_count": "多烫登记", "multi_press_ratio_percent": "多烫占比%",
    })
    st.dataframe(display[[
        "周开始", "平台", "登记单数", "周登记占比%", "膜数", "周膜数占比%",
        "卫衣登记", "卫衣占比%", "多烫登记", "多烫占比%",
    ]], hide_index=True, width="stretch")


def _render_platform_people(rows):
    display = rows.rename(columns={
        "platform": "平台", "hotstamp_person": "烫印人员",
        "registration_count": "登记单数", "registration_share_percent": "平台登记占比%",
        "film_quantity": "膜数", "film_share_percent": "平台膜数占比%",
        "hoodie_registration_count": "卫衣登记", "multi_press_registration_count": "多烫登记",
    })
    st.dataframe(display[[
        "平台", "烫印人员", "登记单数", "平台登记占比%", "膜数",
        "平台膜数占比%", "卫衣登记", "多烫登记",
    ]], hide_index=True, width="stretch")


def _render_people(rows):
    display = rows.rename(columns={
        "hotstamp_person": "烫印人员", "registration_count": "登记单数",
        "registration_share_percent": "总登记占比%", "film_quantity": "膜数",
        "film_share_percent": "总膜数占比%", "hoodie_registration_count": "卫衣登记",
        "hoodie_ratio_percent": "卫衣占个人登记%", "multi_press_registration_count": "多烫登记",
        "multi_press_ratio_percent": "多烫占个人登记%", "hansen_registration_count": "汉森登记",
        "hansen_ratio_percent": "汉森占个人登记%",
    })
    st.dataframe(display[[
        "烫印人员", "登记单数", "总登记占比%", "膜数", "总膜数占比%",
        "卫衣登记", "卫衣占个人登记%", "多烫登记", "多烫占个人登记%",
        "汉森登记", "汉森占个人登记%",
    ]], hide_index=True, width="stretch")


def _render_daily(rows):
    display = rows.rename(columns={
        "business_date": "日期", "registration_count": "登记单数",
        "film_quantity": "膜数", "hoodie_registration_count": "卫衣登记",
        "multi_press_registration_count": "多烫登记",
        "white_board_registration_count": "白板登记",
    })
    st.line_chart(display.set_index("日期")[["登记单数", "膜数"]])
    st.dataframe(display[[
        "日期", "登记单数", "膜数", "卫衣登记", "多烫登记", "白板登记",
    ]], hide_index=True, width="stretch")


def _render_migration_error(exc):
    st.error(f"人工登记数据加载失败：{exc}")
    st.info("请重新执行 sql/after_sales/03_hotstamp_film_audit.sql。")


def _percent(value, total):
    return value / total * 100 if total else 0.0
