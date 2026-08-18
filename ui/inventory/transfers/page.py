import streamlit as st

from db.inventory.warehouses import (
    load_transfer_lines,
    load_transfer_orders,
    load_warehouse_balances,
    load_warehouse_inventory_items,
    load_warehouses,
)
from ui.inventory.transfers.distribution import render_distribution
from ui.inventory.transfers.processing import render_transfer_processing
from ui.inventory.transfers.request import render_restock_request
from utils.auth import has_permission


def render_warehouse_transfer_page(supabase):
    st.title("仓库分布与调拨")
    st.caption(
        "25仓负责主要衣服出库；60仓、70仓主要存储。"
        "库位仅作参考，不作为操作必填项。"
    )
    saved = st.session_state.pop("warehouse_transfer_saved", None)
    if saved:
        st.success(saved)

    try:
        warehouses = load_warehouses(supabase)
        items = load_warehouse_inventory_items(supabase)
        balances = load_warehouse_balances(supabase)
        orders = load_transfer_orders(supabase)
        all_lines = load_transfer_lines(supabase)
    except Exception:
        st.error("仓库调拨功能尚未初始化。")
        st.info("请按顺序运行 sql/inventory/warehouses/ 目录内的迁移脚本。")
        return

    can_edit = has_permission("can_edit_inventory")
    tabs = st.tabs(["库存分布", "断码补货", "调拨处理与历史"])
    with tabs[0]:
        render_distribution(
            supabase, warehouses, items, balances, orders, all_lines, can_edit
        )
    with tabs[1]:
        render_restock_request(
            supabase, warehouses, items, balances, can_edit
        )
    with tabs[2]:
        render_transfer_processing(
            supabase, warehouses, items, balances, orders, all_lines, can_edit
        )
