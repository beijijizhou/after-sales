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
from ui.inventory.container.form import render_container_form
from ui.inventory.container.tables import (
    render_container_dataframe,
    render_container_detail,
)
from ui.inventory.shared.filters import render_department_category_filters
from utils.auth import has_permission


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_in_transit_table(supabase, department, category):
    st.subheader("在途货柜")
    st.caption("仅显示尚未到货或已经延迟的货柜")
    try:
        raw_df = load_inventory_containers(
            supabase, department=department, category=category,
            statuses=["未到货", "延迟"],
        )
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
    col3.metric("延迟货柜", display_df.loc[
        display_df["状态"] == "延迟", "货柜记录ID"
    ].nunique())
    today = datetime.now(NY_TIMEZONE).date()
    progress_df = build_container_progress_summary(raw_df, today)
    selection_df = progress_df.drop(columns=["货柜记录ID"])
    selection = st.dataframe(
        selection_df,
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"transit_progress_{department}_{category}",
        column_config={
            "发货日期": st.column_config.DateColumn("发货日期"),
            "预计到货日期": st.column_config.DateColumn("预计到货日期"),
            "已运输天数": st.column_config.NumberColumn("已运输天数", format="%d 天"),
            "剩余天数": st.column_config.NumberColumn("剩余天数", format="%d 天"),
            "运输进度": st.column_config.ProgressColumn(
                "运输进度", min_value=0, max_value=100, format="%d%%"
            ),
            "总件数": st.column_config.NumberColumn("总件数", format="%d"),
        },
    )
    selected_rows = selection.selection.rows
    if selected_rows:
        container_key = progress_df.iloc[selected_rows[0]]["货柜记录ID"]
        render_container_detail(display_df, container_key)
        if has_permission("can_edit_container"):
            render_status_update(supabase, raw_df, container_key)
    return raw_df


def render_arrival_history_table(supabase, department, category):
    st.subheader("到货记录")
    today = datetime.now(NY_TIMEZONE).date()
    col1, col2 = st.columns(2)
    start_date = col1.date_input(
        "实际到货开始", value=today - timedelta(days=90), key="arrival_start"
    )
    end_date = col2.date_input(
        "实际到货结束", value=today, key="arrival_end"
    )
    try:
        raw_df = load_inventory_containers(
            supabase, start_date, end_date, department, category,
            statuses=["已到货"], date_field="actual_arrival_date",
        )
    except Exception as error:
        st.error(f"到货历史加载失败：{error}")
        st.info("请先在 Supabase SQL Editor 运行 sql/inventory_container_history.sql")
        return pd.DataFrame()
    display_df = build_container_display(
        raw_df, include_cost=has_permission("can_view_cost")
    )
    if display_df.empty:
        st.info("当前日期范围内没有已到货货柜")
        return raw_df
    col1, col2 = st.columns(2)
    col1.metric("已到货总件数", int(display_df["总件数"].sum()))
    col2.metric("到货柜数", display_df["货柜记录ID"].nunique())
    render_container_dataframe(display_df)
    return raw_df


def render_inventory_container_page(supabase):
    st.title("货柜安排")
    try:
        dimensions = load_container_dimensions(supabase)
    except Exception:
        dimensions = pd.DataFrame(columns=["department", "category"])
    department, category = render_department_category_filters(
        dimensions, key="container_shared"
    )
    transit_tab, create_tab, arrival_tab = st.tabs([
        "在途货柜", "新增货柜", "到货历史",
    ])
    with transit_tab:
        render_in_transit_table(supabase, department, category)
    with create_tab:
        if has_permission("can_edit_container"):
            render_container_form(supabase, department, category)
        else:
            st.info("当前账号只能查看货柜安排，不能新增或修改")
    with arrival_tab:
        arrived_df = render_arrival_history_table(supabase, department, category)
        render_container_history(supabase, arrived_df)
