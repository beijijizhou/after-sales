from datetime import timedelta

import pandas as pd
import streamlit as st

from db.inventory.container.repository import load_inventory_containers
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
    quantities = pd.to_numeric(
        raw_df["quantity"], errors="coerce"
    ).fillna(0)
    col1, col2 = st.columns(2)
    col1.metric("到柜总件数", int(quantities.sum()))
    col2.metric("到柜数量", raw_df["container_key"].nunique())
    render_container_inventory_summary(
        raw_df, "到柜库存汇总"
    )
    render_container_records(
        raw_df,
        include_cost=has_permission("can_view_cost"),
    )
    return raw_df


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
