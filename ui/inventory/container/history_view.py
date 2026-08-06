from datetime import timedelta

import pandas as pd
import streamlit as st

from db.inventory.container.repository import load_inventory_containers
from db.inventory.container.history import (
    attach_arrival_confirmation_times,
    load_container_events,
)
from db.inventory.container.tables import sort_arrival_history_rows
from ui.inventory.container.tables import (
    render_container_inventory_summary,
    render_container_records,
)
from utils.auth import has_permission


def render_arrival_history_table(
    supabase, start_date, end_date, department, category,
    brands, materials, colors, sizes,
):
    st.subheader("到柜记录")
    try:
        raw_df = load_inventory_containers(
            supabase, start_date, end_date, department, category,
            statuses=["已到柜", "已入库", "已到货"],
            date_field="actual_arrival_date",
            brands=brands, materials=materials, colors=colors, sizes=sizes,
        )
    except Exception as error:
        st.error(f"到柜历史加载失败：{error}")
        return pd.DataFrame()
    if raw_df.empty:
        st.info("当前日期范围内没有到柜记录")
        return raw_df
    try:
        raw_df = attach_arrival_confirmation_times(
            raw_df, load_container_events(supabase)
        )
    except Exception as error:
        st.warning(f"确认到柜时间加载失败，暂按实际到货时间排序：{error}")
    quantities = pd.to_numeric(
        raw_df["quantity"], errors="coerce"
    ).fillna(0)
    col1, col2 = st.columns(2)
    col1.metric("到柜总件数", int(quantities.sum()))
    col2.metric("到柜数量", raw_df["container_key"].nunique())
    render_container_inventory_summary(
        raw_df, "到柜库存汇总"
    )
    st.subheader("到柜明细")
    sort_label = st.segmented_control(
        "记录排序",
        ["按到柜时间", "按部门"],
        default="按到柜时间",
        key="container_arrival_history_sort",
    ) or "按到柜时间"
    group_by_department = sort_label == "按部门"
    sorted_df = sort_arrival_history_rows(
        raw_df,
        mode="department" if group_by_department else "time",
    )
    render_container_records(
        sorted_df,
        include_cost=has_permission("can_view_cost"),
        group_by_department=group_by_department,
    )
    return sorted_df


def render_arrival_date_range(today):
    selected = st.date_input(
        "实际到柜日期",
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
