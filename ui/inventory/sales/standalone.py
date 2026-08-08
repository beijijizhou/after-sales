import streamlit as st

from db.inventory import load_inventory_dimensions
from db.inventory.master_data.repository import load_sku_catalog
from ui.inventory.sales.page import render_customer_sales_outbound
from utils.auth import has_permission


def render_customer_sales_page(supabase):
    st.title("客户销售出库")
    st.caption("维护客户、销售出库和 Invoice；与生产领用库存分开管理。")
    try:
        dimensions = load_inventory_dimensions(supabase)
    except Exception:
        st.error("库存资料加载失败，请刷新后重试。")
        return
    if dimensions.empty:
        st.warning("暂无可销售的库存 SKU。")
        return

    departments = _values(dimensions, "department")
    default_department = "DTF" if "DTF" in departments else departments[0]
    department = _select_with_reset(
        "销售库存部门", departments, "customer_sales_department",
        default_department,
    )
    scoped = dimensions[dimensions["department"] == department]
    categories = _values(scoped, "category")
    default_category = (
        "黑白短袖" if "黑白短袖" in categories else categories[0]
    )
    category = _select_with_reset(
        "销售品类", categories, "customer_sales_category_filter",
        default_category,
    )
    try:
        raw_df = load_sku_catalog(supabase, department)
        raw_df = raw_df[raw_df["category"] == category]
        if "is_active" in raw_df:
            raw_df = raw_df[raw_df["is_active"].fillna(True)]
    except Exception:
        st.error("销售库存加载失败，请刷新后重试。")
        return
    render_customer_sales_outbound(
        supabase,
        department,
        category,
        raw_df,
        has_permission("can_edit_inventory"),
        show_heading=False,
    )


def _select_with_reset(label, options, key, default):
    if st.session_state.get(key) not in options:
        st.session_state[key] = default
    return st.selectbox(label, options, key=key)


def _values(frame, column):
    return sorted({
        str(value).strip() for value in frame[column].dropna()
        if str(value).strip()
    })
