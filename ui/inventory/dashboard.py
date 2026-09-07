from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from db.inventory.dashboard import (
    load_daily_completion_status,
)
from db.inventory.operations.daily_outbound_versions import (
    acknowledge_no_daily_outbound,
)
from ui.inventory.dashboard_overview import (
    history_period,
    render_completion_overview as _render_completion_overview,
    render_overview as _render_overview,
)
from utils.auth import get_current_operator_name
from utils.auth import has_permission


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_inventory_dashboard(supabase):
    st.title("库存总结")
    saved_message = st.session_state.pop(
        "inventory_dashboard_saved_message", None
    )
    error_message = st.session_state.pop(
        "inventory_dashboard_error_message", None
    )
    if saved_message:
        st.success(saved_message)
    if error_message:
        st.error(error_message)
    st.caption(
        "集中查看生产库存、耗材库存、货柜安排和每日消耗完成情况。"
    )
    today = datetime.now(NY_TIMEZONE).date()
    _render_overview(supabase, today)
    st.divider()
    _render_daily_completion(supabase, today)


def _render_daily_completion(supabase, today):
    st.subheader("每日出库完成情况")
    st.caption(
        "统一查看每日出库完成情况。黑白短袖、彩色短袖和 UV "
        "均由人工表格确认正式出库；系统数据只在库存页面辅助核对。"
    )
    try:
        summary, completed, start_date = load_daily_completion_status(
            supabase, today
        )
    except Exception as error:
        st.error(f"每日出库状态加载失败：{error}")
        return {}
    missing = int(summary["待处理天数"].sum())
    history_end, check_days = history_period(today, start_date)
    _render_completion_overview(
        summary, completed, today, start_date,
        history_end, check_days, missing,
    )
    _render_no_outbound_acknowledgement(supabase)


def _render_no_outbound_acknowledgement(supabase):
    movement_date = st.session_state.get(
        "inventory_no_outbound_ack_date"
    )
    if movement_date is None:
        return
    project = st.session_state.get(
        "inventory_no_outbound_ack_project", "黑白短袖"
    )
    department = "UV" if project == "UV 生产库存" else "DTF"
    category = "" if department == "UV" else project
    st.markdown("#### 确认当日无出库")
    st.info(
        f"{movement_date:%Y-%m-%d}｜{project}：确认当日无出库。"
        "保存后只完成核对，不改变库存，不计入消耗。"
    )
    left, right = st.columns(2)
    if left.button(
        "取消", key="inventory_no_outbound_cancel", width="stretch"
    ):
        st.session_state.pop("inventory_no_outbound_ack_date", None)
        st.session_state.pop("inventory_no_outbound_ack_project", None)
        st.rerun()
    confirmed = st.checkbox(
        "我已核对当日确实没有仓库出货",
        key="inventory_no_outbound_confirm",
    )
    if not right.button(
        "保存无出库确认",
        type="primary", width="stretch",
        disabled=not confirmed or not has_permission("can_edit_inventory"),
        key="inventory_no_outbound_save",
    ):
        return
    try:
        acknowledge_no_daily_outbound(
            supabase, department, category, movement_date,
            get_current_operator_name(), "确认当日无出库、无调货",
        )
    except Exception as error:
        st.error(f"无出库确认保存失败：{error}")
        return
    st.session_state.pop("inventory_no_outbound_ack_date", None)
    st.session_state.pop("inventory_no_outbound_ack_project", None)
    st.session_state["inventory_dashboard_saved_message"] = (
        f"{movement_date:%m/%d} {project}已确认无出库；库存未变动。"
    )
    st.rerun()
