import streamlit as st

from db.inventory import (
    SIZE_COLUMNS,
    load_inventory_dimensions,
    load_inventory_items,
)
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
