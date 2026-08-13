"""Consumable SKU creation form."""

import streamlit as st

from db.consumables import create_consumable_item
from ui.consumables.sku_models import copy_defaults, copy_options
from utils.auth import get_current_operator_name


def render_create_form(supabase, department_id, items, can_manage):
    st.subheader("新增耗材 SKU")
    if not can_manage:
        st.info("当前账号只有查看权限，不能新增耗材 SKU。")
        return
    options, labels = copy_options(items)
    source_id = st.selectbox("复制现有耗材 SKU（可选）", options, format_func=lambda value: labels.get(value, "不复制，从空白新增"), key="consumable_sku_copy_source", help="复制后保留耗材名称和计数单位，只需修改规格、品牌和每箱数量。")
    defaults = copy_defaults(items, source_id)
    if source_id:
        st.caption("已固定分类、耗材名称、基础单位和包装单位；请修改规格/型号、品牌及每箱数量。")
    with st.form(f"create_consumable_sku_{source_id or 'blank'}"):
        col1, col2 = st.columns(2)
        category = col1.text_input("分类 *", value=defaults["category"], placeholder="例如：膜", disabled=bool(source_id))
        name = col2.text_input("耗材名称 *", value=defaults["name"], placeholder="例如：DTF转印膜", disabled=bool(source_id))
        col1, col2 = st.columns(2)
        specification = col1.text_input("规格/型号（可选）", value=defaults["specification"], placeholder="例如：200米/卷")
        brand = col2.text_input("品牌（可选）", value=defaults["brand"])
        col1, col2 = st.columns(2)
        base_unit = col1.text_input("基础单位 *", value=defaults["base_unit"], placeholder="瓶、卷、米", disabled=bool(source_id))
        minimum_boxes = col2.number_input("最低库存（箱，可选）", min_value=0.0, value=defaults["minimum_boxes"], step=1.0, format="%.2f")
        col1, col2 = st.columns(2)
        col1.text_input("计数单位", value="箱", disabled=True)
        units_per_package = col2.number_input("每箱数量 *", min_value=0.0001, value=defaults["units_per_package"], step=0.1, format="%.4f")
        submitted = st.form_submit_button("新增耗材 SKU", type="primary", width="stretch")
    if not submitted:
        return
    if not category.strip() or not name.strip() or not base_unit.strip():
        st.error("请填写所有带 * 的必填项目。")
        return
    values = {"department_id": department_id, "category": category.strip(), "name": name.strip(), "specification": specification.strip(), "brand": brand.strip(), "base_unit": base_unit.strip(), "package_unit": "箱", "units_per_package": units_per_package, "minimum_quantity": float(minimum_boxes) * float(units_per_package), "created_by": get_current_operator_name()}
    try:
        create_consumable_item(supabase, values)
    except Exception as error:
        st.error("这个耗材 SKU 已经存在，请在“现有 SKU”中修改。" if "duplicate" in str(error).lower() else f"新增耗材 SKU 失败：{error}")
        return
    st.session_state["consumable_saved_message"] = f"已新增耗材 SKU：{name.strip()}"
    st.rerun()
