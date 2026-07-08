from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from db.inventory import (
    SIZE_COLUMNS,
    build_inventory_table,
    load_inventory_items,
)
from ui.inventory_forms import (
    render_adjust_form,
    render_excel_adjustment,
    render_new_sku_form,
)
from ui.inventory_history import render_inventory_history


def render_setup_help():
    sql_path = Path(__file__).resolve().parent.parent / "sql" / "inventory_tables.sql"
    st.info("第一次使用库存页，请先在 Supabase SQL Editor 运行下面这段 SQL")
    with st.expander("显示库存建表 SQL", expanded=True):
        st.code(sql_path.read_text(), language="sql")


def render_inventory_metrics(inventory_df):
    total_inventory = int(inventory_df["总库存"].sum())
    sku_group_count = len(inventory_df)

    col1, col2 = st.columns(2)
    col1.metric("总库存", total_inventory)
    col2.metric("材质颜色组合", sku_group_count)


def render_inventory_table(inventory_df):
    st.subheader("彩色 T-shirt 库存明细")
    current_date = datetime.now(ZoneInfo("America/New_York")).date()
    st.info(f"当前日期：{current_date}")
    st.dataframe(
        inventory_df, hide_index=True, use_container_width=True,
        column_config={
            "总库存": st.column_config.NumberColumn("总库存"),
            **{size: st.column_config.NumberColumn(size) for size in SIZE_COLUMNS},
        },
    )

def render_inventory_summary(supabase):
    st.title("库存")

    try:
        raw_df = load_inventory_items(supabase)
        inventory_df = build_inventory_table(raw_df)
        if inventory_df.empty:
            st.warning("暂无库存数据")
            render_setup_help()
            st.stop()

        render_inventory_table(inventory_df)
        render_inventory_metrics(inventory_df)
        render_excel_adjustment(supabase)
        with st.expander("少量手动调整"):
            render_adjust_form(supabase, inventory_df)
        with st.expander("新增 SKU"):
            render_new_sku_form(supabase, inventory_df)
        if st.button("按日期查看库存 / SKU 历史", use_container_width=True):
            st.session_state["show_inventory_history"] = True
        if st.session_state.get("show_inventory_history"):
            render_inventory_history(supabase)

    except Exception as e:
        st.error(f"库存数据加载失败：{e}")
        render_setup_help()
