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
    build_weekly_person_special_mix,
    build_weekly_platform_allocation,
    build_weekly_platform_summary,
    prepare_comparison,
)


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_audit_view(supabase):
    st.subheader("每周平台订单分配分析")
    today = datetime.now(NY_TIMEZONE).date()
    current_week_start = today - timedelta(days=today.weekday())
    controls = st.columns([2, 1])
    selected_day = controls[0].date_input(
        "选择所在周",
        value=current_week_start,
        max_value=today,
        key="hotstamp_film_week",
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
    start_date = selected_day - timedelta(days=selected_day.weekday())
    end_date = start_date + timedelta(days=6)
    st.caption(f"统计周期：{start_date} 至 {end_date}")
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

    allocation = build_weekly_platform_allocation(comparison, tolerance)
    summary = build_weekly_platform_summary(allocation, tolerance)
    special_mix = build_weekly_person_special_mix(comparison)
    _render_weekly_metrics(comparison, allocation)
    _render_rule_explanation(tolerance)
    platform_options = ["全部平台", *sorted(allocation["platform"].unique())]
    selected_platform = st.selectbox(
        "查看平台", platform_options, key="weekly_allocation_platform"
    )
    shown_allocation = allocation
    if selected_platform != "全部平台":
        shown_allocation = allocation[allocation["platform"] == selected_platform]
    summary_tab, allocation_tab, mix_tab, gap_tab = st.tabs([
        "平台周汇总", "人员分配占比", "特殊订单占比", "系统差异明细",
    ])
    with summary_tab:
        _render_platform_summary(summary)
    with allocation_tab:
        _render_platform_allocation(shown_allocation)
    with mix_tab:
        _render_person_special_mix(special_mix)
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


def _render_weekly_metrics(comparison, allocation):
    orders = int(comparison["source_entry_count"].sum())
    people = allocation.loc[
        allocation["active_worker"], "hotstamp_person"
    ].nunique()
    attention = int((allocation["allocation_status"] != "均匀").sum())
    hansen_orders = int(comparison.loc[
        comparison["platform"] == "汉森", "source_entry_count"
    ].sum())
    columns = st.columns(4)
    columns[0].metric("本周人工登记单", f"{orders:,}")
    columns[1].metric("参与烫印人数", f"{people:,}")
    columns[2].metric("分配需关注人次", f"{attention:,}")
    columns[3].metric("汉森订单占比", f"{_percent(hansen_orders, orders):.1f}%")


def _render_rule_explanation(tolerance):
    with st.expander("核对口径和平台规范化规则"):
        st.markdown(
            f"- 均匀度：按自然周和平台汇总 Google Sheets 人工登记单，每人应占 "
            f"`100% ÷ 该平台参与人数`；相对偏差在 ±{tolerance}% 内为“均匀”。\n"
            "- 卫衣、多烫和汉森占比都仅使用人工登记行统计。\n"
            "- 原表没有独立的“多件”字段，因此不推测、不统计多件占比。\n"
            "- 系统扫码仅用于“系统差异明细”，不参与分配均匀度和特殊占比。\n"
            "- 系统折算件数：每条扫码按 `multiple_count` 至少 1 件折算。\n"
            "- 平台仅做公开规范化：haloo→Haloo、7创→七创、"
            "SDS-1/SDS1→SDS1、SDS-2/SDS2→SDS2、PT莆田→莆田。\n"
            "- 人员姓名不自动替换；姓名不一致会作为差异直接显示。"
        )


def _render_platform_summary(summary):
    display = summary.rename(columns={
        "platform": "平台", "order_count": "本周登记单数",
        "worker_count": "参与人数", "expected_share_percent": "每人应占%",
        "highest_order_share": "最高人员占比%", "lowest_order_share": "最低人员占比%",
        "order_share_spread": "最高最低差%", "attention_workers": "需关注人数",
        "hoodie_ratio_percent": "卫衣登记占比%", "multi_press_ratio_percent": "多烫登记占比%",
    })
    columns = [
        "平台", "本周登记单数", "参与人数", "每人应占%", "最高人员占比%",
        "最低人员占比%", "最高最低差%", "需关注人数", "卫衣登记占比%",
        "多烫登记占比%",
    ]
    st.dataframe(display[columns], hide_index=True, width="stretch")


def _render_platform_allocation(allocation):
    display = allocation.rename(columns={
        "platform": "平台", "hotstamp_person": "烫印人员",
        "source_entry_count": "登记单数", "order_share_percent": "平台登记占比%",
        "expected_share_percent": "应占%", "order_deviation_percent": "相对偏差%",
        "allocation_status": "分配状态", "hoodie_entry_count": "卫衣登记单",
        "hoodie_allocation_share_percent": "平台卫衣占比%",
        "multi_press_entry_count": "多烫登记单", "multi_press_allocation_share_percent": "平台多烫占比%",
    })
    columns = [
        "平台", "烫印人员", "登记单数", "平台登记占比%", "应占%", "相对偏差%",
        "分配状态", "卫衣登记单", "平台卫衣占比%", "多烫登记单", "平台多烫占比%",
    ]
    st.dataframe(display[columns], hide_index=True, width="stretch")


def _render_person_special_mix(mix):
    display = mix.rename(columns={
        "hotstamp_person": "烫印人员", "order_count": "全部登记单数",
        "hoodie_entry_count": "卫衣登记单", "hoodie_ratio_percent": "卫衣登记占比%",
        "multi_press_entry_count": "多烫登记单", "multi_press_ratio_percent": "多烫登记占比%",
        "hansen_order_count": "汉森登记单", "hansen_ratio_percent": "汉森登记占比%",
    })
    columns = [
        "烫印人员", "全部登记单数", "卫衣登记单", "卫衣登记占比%", "多烫登记单",
        "多烫登记占比%", "汉森登记单", "汉森登记占比%",
    ]
    st.dataframe(display[columns], hide_index=True, width="stretch")


def _percent(value, total):
    return value / total * 100 if total else 0.0


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
