from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from automation.sync.daily_inventory_consumption import (
    COLORED_FAST_PLATFORM_SCOPE,
    load_automatic_daily_batch_previews,
)
from automation.sync.daily import (
    COLORED_PRIMARY_PLATFORMS,
    sync_production_day,
)
from db.inventory.dashboard import (
    build_automatic_missing_dates,
    load_daily_completion_status,
)
from ui.inventory.dashboard_overview import (
    history_period,
    render_completion_overview as _render_completion_overview,
    render_overview as _render_overview,
)
from ui.inventory.dashboard_batch_view import (
    format_applied_result as _format_applied_result,
    render_batch_preview,
    system_stock_change_display as _system_stock_change_display,
)
from ui.inventory.planning.uv_source import (
    google_sheets_client,
    render_uv_spreadsheet_selector,
)
from utils.auth import get_current_operator_name


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
    st.subheader("每日库存扣减")
    st.caption(
        "统一查看历史补录、今日进度，并处理彩色短袖和 UV 的系统扣减。"
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
    automatic_missing_dates = build_automatic_missing_dates(
        completed, start_date, history_end
    )
    requested_flow = _render_completion_overview(
        summary, completed, today, start_date,
        history_end, check_days, missing,
    )
    scope_key = "inventory_dashboard_auto_flow_scope"
    if requested_flow:
        st.session_state[scope_key] = requested_flow
    active_flow = st.session_state.get(scope_key)
    selected_missing_dates = (
        _filter_automatic_missing_dates(
            automatic_missing_dates, active_flow
        )
        if active_flow else automatic_missing_dates
    )
    if active_flow and not selected_missing_dates:
        st.session_state.pop(scope_key, None)
        active_flow = None
        selected_missing_dates = automatic_missing_dates
    _render_automatic_daily_operation(
        supabase, selected_missing_dates,
        auto_load=bool(requested_flow),
        flow_scope=active_flow,
    )


def _filter_automatic_missing_dates(missing_dates, flow_label):
    return {
        movement_date: flow_label
        for movement_date, labels in missing_dates.items()
        if flow_label in str(labels)
    }


def _render_automatic_daily_operation(
    supabase, missing_dates, auto_load=False, flow_scope=None
):
    if not missing_dates:
        st.success("彩色短袖和 UV 在当前检查范围内均已完成扣减。")
        return
    labels = "、".join(str(value) for value in missing_dates.values())
    needs_colored = "彩色短袖" in labels
    needs_uv = "UV 生产库存" in labels
    st.markdown("#### 系统待补处理")
    if flow_scope:
        scope_columns = st.columns([3, 1])
        scope_columns[0].info(f"当前仅预览：{flow_scope}")
        if scope_columns[1].button(
            "查看全部",
            key="inventory_dashboard_show_all_auto_flows",
            width="stretch",
        ):
            st.session_state.pop(
                "inventory_dashboard_auto_flow_scope", None
            )
            st.rerun()
    source_descriptions = []
    if needs_colored:
        source_descriptions.append("彩色短袖生产数据")
    if needs_uv:
        source_descriptions.append("UV Google Sheets")
    st.caption("预览并补扣" + "和".join(source_descriptions) + "。")
    if needs_colored:
        st.info(
            f"彩色短袖快速补录平台：{COLORED_FAST_PLATFORM_SCOPE}。"
            "其他低量平台不阻塞本次补录，完整生产数据仍由生产数据页面核对。"
        )
    options = sorted(missing_dates)
    st.caption(
        "待补扣日期：" + "；".join(
            f"{value:%Y-%m-%d}（{missing_dates[value]}）"
            for value in options
        )
    )
    if needs_uv:
        spreadsheet = render_uv_spreadsheet_selector(
            key="inventory_dashboard_uv_spreadsheet"
        )
    else:
        spreadsheet = {"id": ""}
    state_key = "inventory_dashboard_auto_previews"
    identity_key = "inventory_dashboard_auto_preview_identity"
    identity = (
        tuple(
            (value.isoformat(), missing_dates[value])
            for value in options
        ),
        spreadsheet["id"],
    )
    load_requested = st.button(
        "一键读取全部待补日期",
        type="secondary",
        width="stretch",
        key="inventory_dashboard_auto_load",
    )
    if auto_load or load_requested:
        sheets_client = None
        if needs_uv:
            try:
                sheets_client = google_sheets_client()
            except Exception:
                sheets_client = None
        secrets = dict(st.secrets)
        progress_rows = {
            movement_date: {
                "日期": movement_date,
                "项目": missing_dates[movement_date],
                "进度": "等待处理",
            }
            for movement_date in options
        }
        progress_status = st.status(
            "正在按天处理补录数据...", expanded=True
        )
        progress_placeholder = progress_status.empty()

        def report_day_progress(movement_date, project, state):
            progress_rows[movement_date] = {
                "日期": movement_date,
                "项目": project,
                "进度": state,
            }
            progress_placeholder.dataframe(
                pd.DataFrame(progress_rows.values()).sort_values("日期"),
                hide_index=True,
                width="stretch",
                column_config={
                    "日期": st.column_config.DateColumn("日期"),
                    "项目": st.column_config.TextColumn("项目"),
                    "进度": st.column_config.TextColumn("进度"),
                },
            )

        with progress_status:
            previews = load_automatic_daily_batch_previews(
                supabase,
                missing_dates,
                sheets_client,
                spreadsheet["id"],
                ensure_colored_source=lambda movement_date: (
                    sync_production_day(
                        movement_date,
                        secrets=secrets,
                        required_platforms=COLORED_PRIMARY_PLATFORMS,
                        supabase=supabase,
                        operator=get_current_operator_name(),
                    )
                ),
                max_day_workers=2,
                report_day_progress=report_day_progress,
            )
        has_errors = any(
            row["进度"] == "生产数据读取失败"
            for row in progress_rows.values()
        )
        progress_status.update(
            label=(
                "补录预览已生成，部分日期读取失败"
                if has_errors else "全部日期的补录预览已生成"
            ),
            state="error" if has_errors else "complete",
            expanded=has_errors,
        )
        st.session_state[state_key] = previews
        st.session_state[identity_key] = identity

    previews = st.session_state.get(state_key)
    if (
        not previews
        or st.session_state.get(identity_key) != identity
    ):
        return
    render_batch_preview(supabase, previews, state_key, identity_key)
