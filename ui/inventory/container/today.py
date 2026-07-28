import pandas as pd
import streamlit as st

from db.inventory.container.repository import load_inventory_containers
from ui.inventory.container.tables import render_container_records
from utils.auth import has_permission


def container_tab_names(has_today_arrivals):
    if has_today_arrivals:
        return ["今日到货", "在途货柜", "新增货柜", "到货历史"]
    return ["在途货柜", "新增货柜", "到货历史", "今日到货"]


def load_today_arrivals(
    supabase, today, department, category,
    brands, materials, colors, sizes,
):
    return load_inventory_containers(
        supabase,
        start_date=today,
        end_date=today,
        department=department,
        category=category,
        statuses=["已到货"],
        date_field="actual_arrival_date",
        brands=brands,
        materials=materials,
        colors=colors,
        sizes=sizes,
    )


def render_today_arrivals(raw_df, load_error=None):
    st.subheader("今日实际到货")
    st.caption("这里只显示仓库已经手动确认、且实际到货日期为今天的货柜。")
    if load_error is not None:
        error = load_error
        st.error(f"今日实际到货加载失败：{error}")
        return
    if raw_df.empty:
        st.info("今天还没有手动确认到货的货柜")
        return

    quantities = pd.to_numeric(
        raw_df["quantity"], errors="coerce"
    ).fillna(0)
    col1, col2 = st.columns(2)
    col1.metric("今日实际到货", raw_df["container_key"].nunique())
    col2.metric("今日到货总件数", int(quantities.sum()))
    render_container_records(
        raw_df,
        include_cost=has_permission("can_view_cost"),
    )
