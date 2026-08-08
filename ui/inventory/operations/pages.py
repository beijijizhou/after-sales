import streamlit as st

from db.consumables import load_consumable_items, load_departments
from ui.consumables.operations import render_movement_entry
from ui.inventory.category_routing import is_consumable_category
from ui.inventory.i18n import t
from ui.inventory.shared.filters import _reset_invalid_selectbox
from ui.inventory.operations.forms import (
    render_adjust_form,
    render_inventory_unit_calculator,
)
from ui.inventory.operations.outbound import render_daily_outbound
from utils.auth import has_permission, is_admin


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
        if is_consumable_category(operation_category):
            _render_consumable_movement_operation(
                supabase, department, can_edit
            )
            return
        operation_inventory_df = inventory_df[
            inventory_df["品类"] == operation_category
        ].reset_index(drop=True)
        render_inventory_unit_calculator()
        render_adjust_form(
            supabase, department, operation_category,
            operation_inventory_df,
        )


def _render_consumable_movement_operation(
    supabase, department_code, can_edit,
):
    st.caption(
        "当前品类是 DTF 耗材；下方直接使用耗材库存和箱数口径，"
        "不会写入服装生产库存。"
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
        items = load_consumable_items(
            supabase, department_id, active_only=True
        )
    except Exception as error:
        st.error(f"耗材数据加载失败：{error}")
        return
    render_movement_entry(
        supabase,
        department_code,
        items,
        can_edit and has_permission("can_edit_consumables"),
        is_admin(),
        movement_options=["入库", "领用"],
        title="DTF 耗材库存调整",
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
