import streamlit as st

from ui.inventory.i18n import t
from ui.inventory.shared.filters import _reset_invalid_selectbox
from ui.inventory.operations.forms import (
    render_adjust_form,
    render_inventory_unit_calculator,
)
from ui.inventory.operations.outbound import render_daily_outbound


def render_daily_outbound_operation(
    supabase, department, category, raw_df, can_edit,
):
    if not can_edit:
        st.info(t("当前账号只有库存查看权限，不能修改库存"))
        return
    operation_category = _select_operation_category(
        category, raw_df, "daily_outbound_category"
    )
    if operation_category:
        render_daily_outbound(
            supabase, department, operation_category
        )


def render_temporary_movement_operation(
    supabase, department, category, raw_df, inventory_df, can_edit,
):
    if not can_edit:
        st.info(t("当前账号只有库存查看权限，不能修改库存"))
        return
    operation_category = _select_operation_category(
        category, raw_df, "temporary_movement_category"
    )
    if operation_category:
        operation_inventory_df = inventory_df[
            inventory_df["品类"] == operation_category
        ].reset_index(drop=True)
        render_inventory_unit_calculator()
        render_adjust_form(
            supabase, department, operation_category,
            operation_inventory_df,
        )
def _select_operation_category(category, raw_df, key):
    if category:
        return category
    if raw_df.empty or "category" not in raw_df.columns:
        st.info(t("当前没有可操作的库存品类"))
        return ""
    category_order = {value: index for index, value in enumerate([
        "黑白短袖", "彩色短袖", "卫衣",
    ])}
    options = sorted({
        str(value).strip() for value in raw_df["category"].dropna()
        if str(value).strip()
    }, key=lambda value: (category_order.get(value, 99), value))
    if not options:
        st.info(t("当前没有可操作的库存品类"))
        return ""
    _reset_invalid_selectbox(key, options)
    st.caption(t("当前查看全部品类，请选择本次库存操作的目标品类"))
    return st.selectbox(t("操作品类"), options, key=key, format_func=t)
