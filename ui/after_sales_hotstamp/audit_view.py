"""Manager-facing film balance and system-difference review."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.after_sales_hotstamp import (
    load_hotstamp_film_batch_rows,
    load_hotstamp_film_batches,
    load_hotstamp_film_comparison,
)
from ui.after_sales_hotstamp.models import (
    build_daily_person_balance,
    build_person_summary,
    prepare_comparison,
)


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_audit_view(supabase):
    st.subheader("烫印膜均匀度与系统差异")
    today = datetime.now(NY_TIMEZONE).date()
    controls = st.columns([2, 1])
    selected_range = controls[0].date_input(
        "核对日期",
        value=(today - timedelta(days=6), today),
        max_value=today,
        key="hotstamp_film_date_range",
    )
    tolerance = controls[1].slider(
        "均匀度允许偏差",
        min_value=5,
        max_value=30,
        value=10,
        step=5,
        format="%d%%",
        key="hotstamp_film_tolerance",
    )
    if not isinstance(selected_range, (tuple, list)) or len(selected_range) != 2:
        st.info("请选择开始和结束日期。")
        return
    start_date, end_date = selected_range
    try:
        raw = load_hotstamp_film_comparison(supabase, start_date, end_date)
    except Exception as exc:
        st.error(f"核对数据加载失败：{exc}")
        st.info(
            "请先在 Supabase SQL Editor 运行 "
            "sql/after_sales/03_hotstamp_film_audit.sql。"
        )
        return
    comparison = prepare_comparison(raw)
    if comparison.empty:
        st.info("所选日期没有表格登记或系统烫印数据。")
        return

    daily = build_daily_person_balance(comparison, tolerance)
    people = build_person_summary(daily, tolerance)
    _render_conclusion_metrics(comparison, daily)
    _render_rule_explanation(tolerance)
    people_tab, daily_tab, gap_tab = st.tabs([
        "人员均匀度", "每日均匀度", "系统差异明细",
    ])
    with people_tab:
        _render_people(people)
    with daily_tab:
        _render_daily(daily)
    with gap_tab:
        _render_gaps(comparison)


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
        "source_file_name": "周表",
        "start_date": "开始日期",
        "end_date": "结束日期",
        "row_count": "有效登记行",
        "total_film_quantity": "膜总数",
        "invalid_row_count": "异常行",
        "operator": "操作人",
        "created_at": "同步时间",
        "status": "状态",
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


def _render_conclusion_metrics(comparison, daily):
    film = int(comparison["film_quantity"].sum())
    scans = int(comparison["system_scan_count"].sum())
    pieces = int(comparison["system_piece_count"].sum())
    unbalanced = int((daily["balance_status"] != "均匀").sum())
    columns = st.columns(4)
    columns[0].metric("表格登记膜数", f"{film:,}")
    columns[1].metric("系统扫码单数", f"{scans:,}", delta=f"差 {film - scans:+,}")
    columns[2].metric("系统折算件数", f"{pieces:,}", delta=f"差 {film - pieces:+,}")
    columns[3].metric("不均匀人次", f"{unbalanced:,}")


def _render_rule_explanation(tolerance):
    with st.expander("核对口径和平台规范化规则"):
        st.markdown(
            f"- 均匀度：同一天每位有膜登记的烫印人员，与当天团队人均膜数比较；"
            f"偏差在 ±{tolerance}% 内标记为“均匀”。\n"
            "- 系统扫码单数：`barcode_scans` 的扫码记录数。\n"
            "- 系统折算件数：每条扫码按 `multiple_count` 至少 1 件折算。\n"
            "- 平台仅做公开规范化：haloo→Haloo、7创→七创、"
            "SDS-1/SDS1→SDS1、SDS-2/SDS2→SDS2、PT莆田→莆田。\n"
            "- 人员姓名不自动替换；姓名不一致会作为差异直接显示。"
        )


def _render_people(people):
    display = people.rename(columns={
        "hotstamp_person": "烫印人员", "active_days": "参与天数",
        "film_quantity": "登记膜数", "system_scan_count": "系统扫码单数",
        "system_piece_count": "系统折算件数", "unbalanced_days": "不均匀天数",
        "max_deviation_percent": "最大偏离", "scan_gap": "膜数-扫码单数",
        "piece_gap": "膜数-折算件数", "balance_status": "均匀状态",
    })
    st.dataframe(display, hide_index=True, width="stretch")


def _render_daily(daily):
    display = daily.rename(columns={
        "business_date": "日期", "hotstamp_person": "烫印人员",
        "film_quantity": "登记膜数", "team_average": "团队人均膜数",
        "balance_deviation_percent": "偏离比例", "balance_status": "均匀状态",
        "system_scan_count": "系统扫码单数", "system_piece_count": "系统折算件数",
        "scan_gap": "膜数-扫码单数", "piece_gap": "膜数-折算件数",
    })
    st.dataframe(display, hide_index=True, width="stretch")


def _render_gaps(comparison):
    only_issues = st.checkbox(
        "只显示有差异或单边缺失的记录",
        value=True,
        key="hotstamp_film_only_issues",
    )
    rows = comparison
    if only_issues:
        rows = rows[rows["match_status"] != "一致"]
    display = rows.rename(columns={
        "business_date": "日期", "hotstamp_person": "烫印人员",
        "platform": "平台", "film_quantity": "登记膜数",
        "system_scan_count": "系统扫码单数",
        "system_piece_count": "系统折算件数",
        "scan_gap": "膜数-扫码单数", "piece_gap": "膜数-折算件数",
        "match_status": "核对状态",
    })
    st.dataframe(display, hide_index=True, width="stretch")
