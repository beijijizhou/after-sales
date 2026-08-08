import streamlit as st

from db.consumables import load_consumable_items, load_departments
from db.inventory import (
    SIZE_COLUMNS,
    load_inventory_dimensions,
    load_inventory_items,
)
from ui.consumables.sku import render_sku_management as render_consumable_skus
from ui.inventory.category_routing import is_consumable_category
from ui.inventory.history.history import (
    load_inventory_history_data,
    render_inventory_history,
    render_sku_operation_history,
)
from ui.inventory.i18n import t
from ui.inventory.shared import render_inventory_dimension_filters
from ui.inventory.sku.initialization import render_inventory_initialization
from ui.inventory.sku.page import render_sku_management
from utils.auth import has_permission


def render_sku_management_page(supabase):
    st.title(t("SKU 管理"))
    try:
        dimensions = load_inventory_dimensions(supabase)
    except Exception as error:
        st.error(f"{t('SKU 主数据加载失败')}：{error}")
        return
    st.markdown(f"#### {t('筛选库存范围')}")
    (
        department, category, brands, materials, colors, sizes,
    ) = render_inventory_dimension_filters(
        dimensions, key="sku_management_filters"
    )
    sku_filters = {
        "category": category,
        "brand": brands,
        "material": materials,
        "color": colors,
        "规格": sizes,
    }
    if is_consumable_category(category):
        _render_consumable_sku_context(supabase, department)
        return
    manage_tab, initialization_tab, import_tab, operation_tab = st.tabs([
        t("SKU 资料与设置"), t("待初始化库存"),
        t("SKU 导入历史"), t("SKU 操作历史"),
    ])
    with manage_tab:
        render_sku_management(
            supabase,
            department,
            has_permission("can_manage_sku"),
            sku_filters,
            selected_category=category,
        )

    with initialization_tab:
        render_inventory_initialization(
            supabase,
            department,
            category,
            has_permission("can_edit_inventory"),
            brands=brands,
            materials=materials,
            colors=colors,
            sizes=sizes,
        )

    try:
        history_data = load_inventory_history_data(
            supabase, department, limit=10000
        )
        inventory_df = load_inventory_items(supabase, department, "")
    except Exception as error:
        with import_tab:
            st.error(f"{t('库存数据加载失败')}：{error}")
        with operation_tab:
            st.error(f"{t('库存数据加载失败')}：{error}")
        return

    visible_sizes = SIZE_COLUMNS if department == "DTF" else None
    with import_tab:
        render_inventory_history(
            supabase,
            department,
            "sku",
            history_data=history_data,
            visible_sizes=visible_sizes,
        )
    with operation_tab:
        render_sku_operation_history(
            inventory_df, history_data, visible_sizes
        )


def _render_consumable_sku_context(supabase, department_code):
    st.caption(
        "当前筛选为 DTF 耗材；新增和修改会保存到耗材库存，"
        "并统一按箱维护包装换算。"
    )
    try:
        departments = load_departments(supabase)
        department_rows = departments[
            departments["code"] == department_code
        ]
        if department_rows.empty:
            st.warning("当前部门尚未建立耗材库存资料。")
            return
        department_id = department_rows.iloc[0]["id"]
        items = load_consumable_items(supabase, department_id)
    except Exception as error:
        st.error(f"耗材 SKU 加载失败：{error}")
        return
    render_consumable_skus(
        supabase,
        department_id,
        items,
        has_permission("can_manage_consumable_sku"),
    )
