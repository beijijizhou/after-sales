import pandas as pd
import streamlit as st

from db.inventory.container.repository import load_inventory_containers
from ui.inventory.container.tables import (
    render_container_inventory_summary,
    render_container_records,
)
from utils.auth import has_permission


def container_tab_names(has_today_arrivals, has_pending_posting=False):
    names = []
    if has_pending_posting:
        names.append("待确认入库")
    if has_today_arrivals:
        names.append("今日到柜")
    names.extend(["在途货柜", "新增货柜", "到柜及入库历史"])
    if not has_today_arrivals:
        names.append("今日到柜")
    if not has_pending_posting:
        names.append("待确认入库")
    return names


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
        statuses=["已到柜", "已入库", "已到货"],
        date_field="actual_arrival_date",
        brands=brands,
        materials=materials,
        colors=colors,
        sizes=sizes,
    )


def render_today_arrivals(raw_df, load_error=None):
    st.subheader("今日到柜")
    st.caption("这里只显示仓库已确认、且真实到柜日期为今天的货柜。")
    if load_error is not None:
        error = load_error
        st.error(f"今日到柜加载失败：{error}")
        return
    if raw_df.empty:
        st.info("今天还没有手动确认到柜的货柜")
        return

    quantities = pd.to_numeric(
        raw_df["quantity"], errors="coerce"
    ).fillna(0)
    col1, col2 = st.columns(2)
    col1.metric("今日到柜", raw_df["container_key"].nunique())
    col2.metric("今日到柜总件数", int(quantities.sum()))
    render_container_inventory_summary(
        raw_df, "今日到柜库存汇总"
    )
    render_container_records(
        raw_df,
        include_cost=has_permission("can_view_cost"),
    )
