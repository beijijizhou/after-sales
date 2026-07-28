from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.inventory.container.repository import (
    load_container_dimensions,
    load_inventory_containers,
)
from db.inventory.container.progress import build_container_progress_summary
from db.inventory.container.tables import build_container_display
from ui.inventory.container.events import (
    render_container_history,
    render_status_update,
)
from ui.inventory.container.filters import (
    render_container_inventory_filters,
)
from ui.inventory.container.form import render_container_form
from ui.inventory.container.tables import (
    render_container_detail,
    render_container_records,
)
from ui.inventory.container.today import (
    container_tab_names,
    load_today_arrivals,
    render_today_arrivals,
)
from ui.inventory.container.week import render_week_selector
from utils.auth import has_permission


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_in_transit_table(
    supabase, start_date, end_date, department, category,
    brands, materials, colors, sizes,
):
    st.subheader("在途货柜")
    st.caption(
        "仅显示尚未到货或已经延迟的货柜；即使未到预计日期，"
        "也可以提前手动确认实际到货。"
    )
    try:
        raw_df = load_inventory_containers(
            supabase, start_date, end_date, department, category,
            statuses=["未到货", "延迟"],
            brands=brands, materials=materials, colors=colors, sizes=sizes,
        )
        today = datetime.now(NY_TIMEZONE).date()
        if start_date <= today <= end_date:
            overdue_df = load_inventory_containers(
                supabase,
                end_date=start_date - timedelta(days=1),
                department=department,
                category=category,
                statuses=["未到货", "延迟"],
                brands=brands,
                materials=materials,
                colors=colors,
                sizes=sizes,
            )
            raw_df = pd.concat(
                [overdue_df, raw_df],
                ignore_index=True,
            ).drop_duplicates()
    except Exception as error:
        st.error(f"在途货柜加载失败：{error}")
        st.info("请先在 Supabase SQL Editor 运行 sql/inventory_container_history.sql")
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
    _render_arrival_alerts(progress_df)
    selection_df = progress_df.drop(columns=["货柜记录ID"])
    selection = st.dataframe(
        selection_df,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key=f"transit_progress_{department}_{category}",
        column_config={
            "发货日期": st.column_config.DateColumn("发货日期"),
            "预计到货日期": st.column_config.DateColumn("预计到货日期"),
            "已运输天数": st.column_config.NumberColumn("已运输天数", format="%d 天"),
            "剩余天数": st.column_config.NumberColumn("剩余天数", format="%d 天"),
            "到货提醒": st.column_config.TextColumn("到货提醒"),
            "运输进度": st.column_config.ProgressColumn(
                "运输进度", min_value=0, max_value=100, format="%d%%"
            ),
            "总件数": st.column_config.NumberColumn("总件数", format="%d"),
        },
    )
    selected_rows = selection.selection.rows
    if selected_rows:
        container_key = progress_df.iloc[selected_rows[0]]["货柜记录ID"]
        target_raw_df = raw_df[raw_df["container_key"] == container_key]
        target_display_df = build_container_display(
            target_raw_df,
            include_cost=has_permission("can_view_cost"),
        )
        render_container_detail(target_display_df, container_key)
        if has_permission("can_edit_container"):
            render_status_update(supabase, raw_df, container_key)
    return raw_df


def _render_arrival_alerts(progress_df):
    delayed = progress_df[progress_df["剩余天数"] < 0]
    arriving = progress_df[
        progress_df["剩余天数"].between(0, 7, inclusive="both")
    ]
    if not delayed.empty:
        labels = "；".join(
            f"{row['货柜号']}（已延迟{abs(int(row['剩余天数']))}天）"
            for _, row in delayed.iterrows()
        )
        st.error(f"延迟到货提醒：{labels}")
    if not arriving.empty:
        labels = "；".join(
            f"{row['货柜号']}（{int(row['剩余天数'])}天）"
            for _, row in arriving.iterrows()
        )
        st.warning(f"一周内到货提醒：{labels}")


def render_arrival_history_table(
    supabase, start_date, end_date, department, category,
    brands, materials, colors, sizes,
):
    st.subheader("到货记录")
    try:
        raw_df = load_inventory_containers(
            supabase, start_date, end_date, department, category,
            statuses=["已到货"], date_field="actual_arrival_date",
            brands=brands, materials=materials, colors=colors, sizes=sizes,
        )
    except Exception as error:
        st.error(f"到货历史加载失败：{error}")
        st.info("请先在 Supabase SQL Editor 运行 sql/inventory_container_history.sql")
        return pd.DataFrame()
    if raw_df.empty:
        st.info("当前日期范围内没有已到货货柜")
        return raw_df
    col1, col2 = st.columns(2)
    quantities = pd.to_numeric(raw_df["quantity"], errors="coerce").fillna(0)
    col1.metric("已到货总件数", int(quantities.sum()))
    col2.metric("到货柜数", raw_df["container_key"].nunique())
    render_container_records(
        raw_df,
        include_cost=has_permission("can_view_cost"),
    )
    return raw_df


def render_inventory_container_page(supabase):
    st.title("货柜安排")
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
    tab_names = container_tab_names(not today_arrivals_df.empty)
    tabs = dict(zip(tab_names, st.tabs(tab_names)))
    with tabs["在途货柜"]:
        week_start, week_end = render_week_selector(
            today,
            show_weekdays=False,
        )
        render_in_transit_table(
            supabase, week_start, week_end, *filters
        )
    with tabs["今日到货"]:
        render_today_arrivals(
            today_arrivals_df,
            load_error=today_arrivals_error,
        )
    with tabs["新增货柜"]:
        if has_permission("can_edit_container"):
            render_container_form(supabase, department, category)
        else:
            st.info("当前账号只能查看货柜安排，不能新增或修改")
    with tabs["到货历史"]:
        arrival_start, arrival_end = _render_arrival_date_range(today)
        arrived_df = render_arrival_history_table(
            supabase, arrival_start, arrival_end, *filters
        )
        render_container_history(supabase, arrived_df)


def _render_arrival_date_range(today):
    selected = st.date_input(
        "实际到货日期",
        value=(today - timedelta(days=30), today),
        max_value=today,
        key="container_arrival_history_dates",
    )
    if isinstance(selected, (tuple, list)):
        if len(selected) >= 2:
            return selected[0], selected[1]
        if len(selected) == 1:
            return selected[0], selected[0]
    return selected, selected
