from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.inventory.container.repository import (
    load_container_dimensions,
    load_inventory_containers,
)
from db.inventory.container.progress import (
    build_container_progress_choices,
    build_container_progress_summary,
)
from db.inventory.container.tables import build_container_display
from ui.inventory.container.events import (
    render_container_history,
    render_status_update,
)
from ui.inventory.container.filters import (
    render_container_inventory_filters,
)
from ui.inventory.container.form import render_container_form
from ui.inventory.container.history_view import (
    render_arrival_date_range,
    render_arrival_history_table,
)
from ui.table_layout import fit_table_height
from ui.inventory.container.item_editor import render_container_item_editor
from ui.inventory.container.posting import (
    load_pending_containers,
    render_pending_container_posting,
)
from ui.inventory.container.search import render_container_search
from ui.inventory.container.progress_view import render_arrival_alerts
from ui.inventory.container.tables import (
    render_container_detail,
    render_filtered_container_summary,
    render_container_inventory_summary,
)
from ui.inventory.container.today import (
    container_tab_names,
    load_today_arrivals,
    render_today_arrival_posting,
    render_today_arrivals,
)
from ui.inventory.container.week import (
    merge_current_week_with_overdue,
    render_week_selector,
)
from utils.auth import has_permission


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_in_transit_table(
    supabase, start_date, end_date, department, category,
    brands, materials, colors, sizes,
):
    st.subheader("在途货柜")
    st.caption(
        "选择货柜后可手动确认到柜日期，日期可以是明天或后天；"
        "也可以一键完成到柜和入库，系统仍会保留完整状态记录。"
        "本周会持续包含尚未确认到柜的逾期货柜。"
    )
    try:
        today = datetime.now(NY_TIMEZONE).date()
        raw_df = load_inventory_containers(
            supabase, start_date, end_date, department, category,
            statuses=["未到货", "延迟", "在途"],
            brands=brands, materials=materials, colors=colors, sizes=sizes,
        )
        if start_date == today and end_date is not None:
            overdue_df = load_inventory_containers(
                supabase, None, today - timedelta(days=1),
                department, category,
                statuses=["未到货", "延迟", "在途"],
                brands=brands, materials=materials, colors=colors,
                sizes=sizes,
            )
            raw_df = merge_current_week_with_overdue(raw_df, overdue_df)
    except Exception as error:
        st.error(f"在途货柜加载失败：{error}")
        st.info("请先在 Supabase SQL Editor 运行 sql/inventory/containers/inventory_container_history.sql")
        return pd.DataFrame()
    display_df = build_container_display(
        raw_df, include_cost=has_permission("can_view_cost")
    )
    if display_df.empty:
        st.info("当前没有符合条件的在途货柜")
        return raw_df
    col1, col2, col3 = st.columns(3)
    col1.metric("在途总件数", int(display_df["总件数"].sum()))
    col2.metric("货柜数量", display_df["货柜记录ID"].nunique())
    expected_dates = pd.to_datetime(
        raw_df["expected_arrival_date"], errors="coerce"
    ).dt.date
    delayed_count = raw_df.loc[
        expected_dates < today, "container_key"
    ].nunique()
    col3.metric("延迟货柜", delayed_count)
    progress_df = build_container_progress_summary(raw_df, today)
    view = st.radio(
        "查看方式",
        ["在途列表", "筛选汇总", "货柜明细"],
        horizontal=True,
        key="transit_container_view",
    )
    if view == "在途列表":
        render_arrival_alerts(progress_df)
        selection_df = progress_df.drop(columns=["货柜记录ID"])
        selected = st.dataframe(
            selection_df,
            hide_index=True,
            width="stretch",
            height=fit_table_height(selection_df),
            on_select="rerun",
            selection_mode="single-row",
            key="transit_container_list_selection",
            column_config={
                "发货日期": st.column_config.DateColumn("发货日期"),
                "预计到货日期": st.column_config.DateColumn("预计到货日期"),
                "已运输天数": st.column_config.NumberColumn(
                    "已运输天数", format="%d 天"
                ),
                "剩余天数": st.column_config.NumberColumn(
                    "剩余天数", format="%d 天"
                ),
                "到货提醒": st.column_config.TextColumn("到货提醒"),
                "运输进度": st.column_config.ProgressColumn(
                    "运输进度", min_value=0, max_value=100,
                    format="%d%%",
                ),
                "总件数": st.column_config.NumberColumn(
                    "总件数", format="%d"
                ),
            },
        )
        if selected.selection.rows:
            selected_index = selected.selection.rows[0]
            container_key = progress_df.iloc[selected_index]["货柜记录ID"]
            _render_transit_container_operation(
                supabase, raw_df, container_key
            )
        else:
            st.caption("点选一行即可查看明细、确认到柜或直接入库。")
    elif view == "筛选汇总":
        render_filtered_container_summary(raw_df)
    else:
        choices = build_container_progress_choices(progress_df)
        selection_key = "transit_container_detail_target"
        options = ["", *choices]
        if st.session_state.get(selection_key, "") not in options:
            st.session_state[selection_key] = ""
        container_key = st.selectbox(
            "查看货柜明细",
            options,
            key=selection_key,
            format_func=lambda value: (
                "请选择货柜" if not value else choices[value]
            ),
        )
        if container_key:
            _render_transit_container_operation(
                supabase, raw_df, container_key
            )
    return raw_df


def _render_transit_container_operation(supabase, raw_df, container_key):
    target_raw_df = raw_df[raw_df["container_key"] == container_key]
    target_display_df = build_container_display(
        target_raw_df,
        include_cost=has_permission("can_view_cost"),
    )
    render_container_detail(
        target_display_df,
        container_key,
        editable_cost=False,
        show_items=False,
    )
    can_edit = has_permission("can_edit_container")
    render_container_item_editor(
        supabase, target_raw_df, container_key, can_edit,
    )
    if can_edit:
        render_status_update(supabase, target_raw_df, container_key)
    else:
        st.info("当前账号可以查看货柜，但不能确认到柜或入库")


def render_inventory_container_page(supabase):
    st.title("货柜安排")
    saved_message = st.session_state.pop("container_saved_message", None)
    if saved_message:
        st.success(saved_message)
    render_container_search(supabase)
    st.divider()
    try:
        dimensions = load_container_dimensions(supabase)
    except Exception:
        dimensions = pd.DataFrame(columns=["department", "category"])
    filters = render_container_inventory_filters(
        dimensions, key="container_shared"
    )
    department, category, brands, materials, colors, sizes = filters
    today = datetime.now(NY_TIMEZONE).date()
    try:
        today_arrivals_df = load_today_arrivals(
            supabase, today, *filters
        )
        today_arrivals_error = None
    except Exception as error:
        today_arrivals_df = pd.DataFrame()
        today_arrivals_error = error
    try:
        pending_df = load_pending_containers(supabase, *filters)
        pending_error = None
    except Exception as error:
        pending_df = pd.DataFrame()
        pending_error = error
    tab_names = container_tab_names(
        not today_arrivals_df.empty,
        not pending_df.empty,
    )
    tabs = dict(zip(tab_names, st.tabs(tab_names)))
    with tabs["在途货柜"]:
        week_start, week_end = render_week_selector(
            today,
            show_weekdays=False,
        )
        render_in_transit_table(
            supabase, week_start, week_end, *filters
        )
    with tabs["今日到柜"]:
        render_today_arrivals(
            today_arrivals_df,
            load_error=today_arrivals_error,
        )
        if today_arrivals_error is None:
            render_today_arrival_posting(
                supabase,
                today_arrivals_df,
            )
    with tabs["待确认入库"]:
        if pending_error is not None:
            st.error(f"待入库货柜加载失败：{pending_error}")
        else:
            render_pending_container_posting(supabase, pending_df)
    with tabs["新增货柜"]:
        if has_permission("can_edit_container"):
            render_container_form(supabase, department, category)
        else:
            st.info("当前账号只能查看货柜安排，不能新增或修改")
    with tabs["到柜及入库历史"]:
        arrival_start, arrival_end = render_arrival_date_range(today)
        arrived_df = render_arrival_history_table(
            supabase, arrival_start, arrival_end, *filters
        )
        render_container_history(supabase, arrived_df)
