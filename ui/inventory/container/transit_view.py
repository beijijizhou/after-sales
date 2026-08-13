"""In-transit container list, summaries, details, and operations."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.inventory.container.progress import build_container_progress_choices, build_container_progress_summary
from db.inventory.container.repository import load_inventory_containers
from db.inventory.container.tables import build_container_display
from ui.inventory.container.events import render_status_update
from ui.inventory.container.item_editor import render_container_item_editor
from ui.inventory.container.progress_view import render_arrival_alerts
from ui.inventory.container.tables import render_container_detail, render_filtered_container_summary
from ui.inventory.container.week import merge_current_week_with_overdue
from ui.table_layout import fit_table_height
from utils.auth import has_permission

NY_TIMEZONE = ZoneInfo("America/New_York")


def render_in_transit_table(supabase, start_date, end_date, department, category, brands, materials, colors, sizes):
    st.subheader("在途货柜")
    st.caption("选择货柜后可手动确认到柜日期，日期可以是明天或后天；也可以一键完成到柜和入库，系统仍会保留完整状态记录。本周会持续包含尚未确认到柜的逾期货柜。")
    try:
        today = datetime.now(NY_TIMEZONE).date()
        raw = load_inventory_containers(supabase, start_date, end_date, department, category, statuses=["未到货", "延迟", "在途"], brands=brands, materials=materials, colors=colors, sizes=sizes)
        if start_date == today and end_date is not None:
            overdue = load_inventory_containers(supabase, None, today - timedelta(days=1), department, category, statuses=["未到货", "延迟", "在途"], brands=brands, materials=materials, colors=colors, sizes=sizes)
            raw = merge_current_week_with_overdue(raw, overdue)
    except Exception as error:
        st.error(f"在途货柜加载失败：{error}")
        st.info("请先在 Supabase SQL Editor 运行 sql/inventory/containers/inventory_container_history.sql")
        return pd.DataFrame()
    display = build_container_display(raw, include_cost=has_permission("can_view_cost"))
    if display.empty:
        st.info("当前没有符合条件的在途货柜")
        return raw
    _render_metrics(raw, display, today)
    progress = build_container_progress_summary(raw, today)
    view = st.radio("查看方式", ["在途列表", "筛选汇总", "货柜明细"], horizontal=True, key="transit_container_view")
    if view == "在途列表":
        _render_progress_list(supabase, raw, progress)
    elif view == "筛选汇总":
        render_filtered_container_summary(raw)
    else:
        _render_detail_selector(supabase, raw, progress)
    return raw


def _render_metrics(raw, display, today):
    columns = st.columns(3)
    columns[0].metric("在途总件数", int(display["总件数"].sum()))
    columns[1].metric("货柜数量", display["货柜记录ID"].nunique())
    dates = pd.to_datetime(raw["expected_arrival_date"], errors="coerce").dt.date
    columns[2].metric("延迟货柜", raw.loc[dates < today, "container_key"].nunique())


def _render_progress_list(supabase, raw, progress):
    render_arrival_alerts(progress)
    table = progress.drop(columns=["货柜记录ID"])
    selected = st.dataframe(table, hide_index=True, width="stretch", height=fit_table_height(table), on_select="rerun", selection_mode="single-row", key="transit_container_list_selection", column_config={
        "发货日期": st.column_config.DateColumn("发货日期"), "预计到货日期": st.column_config.DateColumn("预计到货日期"),
        "已运输天数": st.column_config.NumberColumn("已运输天数", format="%d 天"), "剩余天数": st.column_config.NumberColumn("剩余天数", format="%d 天"),
        "到货提醒": st.column_config.TextColumn("到货提醒"), "运输进度": st.column_config.ProgressColumn("运输进度", min_value=0, max_value=100, format="%d%%"),
        "总件数": st.column_config.NumberColumn("总件数", format="%d"),
    })
    if selected.selection.rows:
        render_transit_operation(supabase, raw, progress.iloc[selected.selection.rows[0]]["货柜记录ID"])
    else:
        st.caption("点选一行即可查看明细、确认到柜或直接入库。")


def _render_detail_selector(supabase, raw, progress):
    choices = build_container_progress_choices(progress)
    key, options = "transit_container_detail_target", ["", *choices]
    if st.session_state.get(key, "") not in options:
        st.session_state[key] = ""
    target = st.selectbox("查看货柜明细", options, key=key, format_func=lambda value: "请选择货柜" if not value else choices[value])
    if target:
        render_transit_operation(supabase, raw, target)


def render_transit_operation(supabase, raw, container_key):
    target = raw[raw["container_key"] == container_key]
    display = build_container_display(target, include_cost=has_permission("can_view_cost"))
    render_container_detail(display, container_key, editable_cost=False, show_items=False)
    can_edit = has_permission("can_edit_container")
    render_container_item_editor(supabase, target, container_key, can_edit)
    if can_edit:
        render_status_update(supabase, target, container_key)
    else:
        st.info("当前账号可以查看货柜，但不能确认到柜或入库")
