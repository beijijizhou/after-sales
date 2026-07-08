from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from db.inventory import (
    DEFAULT_CATEGORY,
    INVENTORY_CATEGORIES,
    SIZE_COLUMNS,
    build_inventory_table,
    load_inventory_items,
)
from ui.inventory_forms import (
    render_adjust_form,
    render_excel_adjustment,
    render_new_sku_form,
)
from ui.inventory_consumption import (
    render_black_white_color_summary,
    render_consumption_model,
    render_consumption_planning_inputs,
    render_reorder_forecast,
)
from ui.inventory_history import render_inventory_history


def render_setup_help():
    sql_path = Path(__file__).resolve().parent.parent / "sql" / "inventory_tables.sql"
    st.info("第一次使用库存页，请先在 Supabase SQL Editor 运行下面这段 SQL")
    with st.expander("显示库存建表 SQL", expanded=True):
        st.code(sql_path.read_text(), language="sql")


def render_category_selector():
    return st.selectbox(
        "库存品类",
        INVENTORY_CATEGORIES,
        index=INVENTORY_CATEGORIES.index(DEFAULT_CATEGORY),
        key="inventory_category",
    )


def render_inventory_metrics(inventory_df):
    table_total = int(inventory_df["总库存"].sum())
    color_count = inventory_df["颜色"].nunique() if "颜色" in inventory_df.columns else 0

    col1, col2 = st.columns(2)
    col1.metric("当前表总库存", table_total)
    col2.metric("当前表颜色数", color_count)


def render_inventory_table(category, inventory_df):
    st.subheader(f"{category} 库存明细")
    current_date = datetime.now(ZoneInfo("America/New_York")).date()
    st.info(f"当前日期：{current_date}")

    st.dataframe(
        inventory_df, hide_index=True, use_container_width=True,
        column_config={
            "成本": st.column_config.NumberColumn("成本", format="%.2f"),
            "总库存": st.column_config.NumberColumn("总库存", format="%d"),
            **{size: st.column_config.NumberColumn(size, format="%d") for size in SIZE_COLUMNS},
        },
    )


def render_inventory_summary(supabase):
    st.title("库存")
    category = render_category_selector()
    st.session_state["inventory_today"] = datetime.now(ZoneInfo("America/New_York")).date()

    try:
        raw_df = load_inventory_items(supabase, category)
        inventory_df = build_inventory_table(raw_df, category)
        if inventory_df.empty:
            st.warning("暂无库存数据")

        render_inventory_table(category, inventory_df)
        render_inventory_metrics(inventory_df)
        render_black_white_color_summary(category, inventory_df)
        order_quantity, arrival_date, buffer_days = render_consumption_planning_inputs(category)
        render_consumption_model(supabase, category, order_quantity)
        render_reorder_forecast(supabase, category, inventory_df, order_quantity, arrival_date, buffer_days)
        render_excel_adjustment(supabase, category)
        with st.expander("少量手动调整"):
            render_adjust_form(supabase, category, inventory_df)
        with st.expander("新增 SKU"):
            render_new_sku_form(supabase, category, inventory_df)
        if st.button("按日期查看库存 / SKU 历史", use_container_width=True):
            st.session_state["show_inventory_history"] = True
        if st.session_state.get("show_inventory_history"):
            render_inventory_history(supabase, category)

    except Exception as e:
        st.error(f"库存数据加载失败：{e}")
        render_setup_help()
