import pandas as pd
import streamlit as st

from db.consumables import (
    load_consumable_batches,
    load_consumable_items,
    load_consumable_movements,
    load_departments,
)
from ui.consumables.operations import (
    render_daily_issue_table,
    render_history,
    render_inventory_initialization,
    render_movement_entry,
    render_reversals,
)
from ui.consumables.sku import render_sku_management
from ui.consumables.stock import (
    build_latest_costs,
    filter_items,
    render_stock,
)
from utils.auth import has_permission, is_admin


def render_consumables_page(supabase):
    st.title("耗材库存")
    saved_message = st.session_state.pop("consumable_saved_message", None)
    if saved_message:
        st.success(saved_message)

    try:
        departments = load_departments(supabase)
    except Exception as error:
        st.error(f"耗材数据加载失败：{error}")
        st.info("请确认耗材库存 SQL 已按顺序运行。")
        return
    if departments.empty:
        st.warning("当前没有可用部门，请先建立库存部门。")
        return

    department_code = _render_department_filter(departments)
    department_id = departments.loc[
        departments["code"] == department_code, "id"
    ].iloc[0]
    try:
        items = load_consumable_items(supabase, department_id)
        batches = load_consumable_batches(supabase, department_id)
        movements = (
            load_consumable_movements(supabase, batches["id"].tolist())
            if not batches.empty else pd.DataFrame()
        )
    except Exception as error:
        st.error(f"耗材数据加载失败：{error}")
        st.info("请确认 sql/consumables 中的文件已经依次运行。")
        return

    filtered_items = _render_item_filters(items)
    filtered_batches, filtered_movements = _filter_history(
        batches, movements, filtered_items
    )
    show_cost = is_admin()
    can_edit = has_permission("can_edit_consumables")
    can_report = can_edit or has_permission("can_report_consumables")
    can_manage_sku = has_permission("can_manage_consumable_sku")
    latest_costs = build_latest_costs(movements)

    stock_tab, issue_tab, operation_tab, history_tab, sku_tab = st.tabs([
        "当前库存", "每日扣减", "库存操作", "历史记录", "SKU 管理",
    ])
    with stock_tab:
        render_stock(filtered_items, latest_costs, show_cost)
    with issue_tab:
        render_daily_issue_table(
            supabase, department_code, filtered_items, can_report
        )
    with operation_tab:
        inbound_tab, initialization_tab = st.tabs([
            "耗材入库", "库存初始化",
        ])
        with inbound_tab:
            render_movement_entry(
                supabase, department_code, filtered_items, can_edit,
                show_cost, movement_options=["入库"], title="耗材入库",
            )
        with initialization_tab:
            render_inventory_initialization(
                supabase, department_code, filtered_items, can_edit, show_cost
            )
    with history_tab:
        movement_tab, reversal_tab = st.tabs(["出入库历史", "撤销"])
        with movement_tab:
            render_history(
                filtered_batches, filtered_movements, items, show_cost
            )
        with reversal_tab:
            render_reversals(
                supabase, filtered_batches, filtered_movements, items,
                can_edit, show_cost,
            )
    with sku_tab:
        render_sku_management(
            supabase, department_id, filtered_items, can_manage_sku
        )


def _render_department_filter(departments):
    options = departments["code"].tolist()
    default_index = options.index("DTF") if "DTF" in options else 0
    labels = dict(zip(departments["code"], departments["name"]))
    return st.selectbox(
        "部门", options, index=default_index,
        format_func=lambda code: labels.get(code, code),
        key="consumable_department",
    )


def _render_item_filters(items):
    if items.empty:
        return items
    category_options = _options(items, "category")
    brand_options = _options(items, "brand")
    col1, col2, col3, col4 = st.columns([1.2, 1.2, 1.4, 1])
    categories = col1.multiselect(
        "分类", category_options, key="consumable_categories"
    )
    brands = col2.multiselect(
        "品牌", brand_options, key="consumable_brands"
    )
    search_text = col3.text_input(
        "名称 / 规格", key="consumable_search"
    )
    active_mode = col4.selectbox(
        "SKU 状态", ["仅启用", "全部", "仅停用"],
        key="consumable_active_mode",
    )
    return filter_items(
        items, categories, brands, search_text, active_mode
    )


def _filter_history(batches, movements, items):
    if batches.empty or movements.empty:
        return batches.iloc[0:0], movements.iloc[0:0]
    item_ids = set(items["id"].astype(str))
    visible_movements = movements[
        movements["item_id"].astype(str).isin(item_ids)
    ].copy()
    batch_ids = set(visible_movements["batch_id"].astype(str))
    visible_batches = batches[
        batches["id"].astype(str).isin(batch_ids)
    ].copy()
    return visible_batches, visible_movements


def _options(df, column):
    return sorted({
        str(value).strip() for value in df[column].dropna()
        if str(value).strip()
    })
