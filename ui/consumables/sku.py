from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.consumables import create_consumable_item, update_consumable_item
from utils.auth import get_current_operator_name


EDIT_COLUMNS = [
    "分类", "耗材名称", "规格/型号", "品牌", "基础单位",
    "包装单位", "每包装数量", "最低库存", "当前库存", "启用",
]


def render_sku_management(
    supabase, department_id, items_df, can_manage
):
    create_tab, catalog_tab = st.tabs(["新增 SKU", "现有 SKU"])
    with create_tab:
        _render_create_form(supabase, department_id, can_manage)
    with catalog_tab:
        _render_catalog(supabase, items_df, can_manage)


def _render_create_form(supabase, department_id, can_manage):
    st.subheader("新增耗材 SKU")
    if not can_manage:
        st.info("当前账号只有查看权限，不能新增耗材 SKU。")
        return

    with st.form("create_consumable_sku"):
        col1, col2 = st.columns(2)
        category = col1.text_input("分类 *", placeholder="例如：墨水")
        name = col2.text_input("耗材名称 *", placeholder="例如：白墨")
        col1, col2 = st.columns(2)
        specification = col1.text_input(
            "规格/型号（可选）", placeholder="例如：1L"
        )
        brand = col2.text_input("品牌（可选）")
        col1, col2 = st.columns(2)
        base_unit = col1.text_input("基础单位 *", placeholder="瓶、卷、米")
        minimum_quantity = col2.number_input(
            "最低库存（可选）", min_value=0.0, value=None,
            step=0.1, format="%.4f",
        )
        has_package = st.checkbox("设置包装换算")
        package_unit = ""
        units_per_package = None
        if has_package:
            col1, col2 = st.columns(2)
            package_unit = col1.text_input(
                "包装单位 *", placeholder="箱、桶、包"
            )
            units_per_package = col2.number_input(
                "每包装数量 *", min_value=0.0001,
                value=1.0, step=0.1, format="%.4f",
            )
        submitted = st.form_submit_button(
            "新增耗材 SKU", type="primary", width="stretch"
        )

    if not submitted:
        return
    if not category.strip() or not name.strip() or not base_unit.strip():
        st.error("请填写所有带 * 的必填项目。")
        return
    if has_package and not package_unit.strip():
        st.error("设置包装换算时，包装单位不能为空。")
        return
    values = {
        "department_id": department_id,
        "category": category.strip(),
        "name": name.strip(),
        "specification": specification.strip(),
        "brand": brand.strip(),
        "base_unit": base_unit.strip(),
        "package_unit": package_unit.strip() or None,
        "units_per_package": units_per_package if has_package else None,
        "minimum_quantity": minimum_quantity,
        "created_by": get_current_operator_name(),
    }
    try:
        create_consumable_item(supabase, values)
    except Exception as error:
        if "duplicate" in str(error).lower():
            st.error("这个耗材 SKU 已经存在，请在“现有 SKU”中修改。")
        else:
            st.error(f"新增耗材 SKU 失败：{error}")
        return
    st.session_state["consumable_saved_message"] = (
        f"已新增耗材 SKU：{name.strip()}"
    )
    st.rerun()


def _render_catalog(supabase, items_df, can_manage):
    st.subheader("现有耗材 SKU")
    if items_df.empty:
        st.info("当前部门还没有耗材 SKU。")
        return
    editor = _build_editor(items_df)
    edited = st.data_editor(
        editor,
        width="stretch",
        hide_index=True,
        disabled=["_id", "当前库存"] if can_manage else ["_id", *EDIT_COLUMNS],
        key="consumable_sku_catalog",
        column_config={
            "_id": None,
            "每包装数量": st.column_config.NumberColumn(
                min_value=0.0001, step=0.1, format="%.4f"
            ),
            "最低库存": st.column_config.NumberColumn(
                min_value=0.0, step=0.1, format="%.4f"
            ),
            "当前库存": st.column_config.NumberColumn(format="%.4f"),
        },
    )
    if not can_manage:
        return
    st.caption("当前库存不能在这里直接修改，请通过入库、领用或库存修正处理。")
    if not st.button("保存 SKU 修改", width="stretch"):
        return
    try:
        updates = _build_updates(items_df, edited)
        for item_id, values in updates:
            update_consumable_item(supabase, item_id, values)
    except Exception as error:
        st.error(f"保存 SKU 失败：{error}")
        return
    if not updates:
        st.info("SKU 信息没有变化。")
        return
    st.session_state["consumable_saved_message"] = (
        f"已保存 {len(updates)} 个耗材 SKU 的修改。"
    )
    st.rerun()


def _build_editor(items_df):
    return pd.DataFrame({
        "_id": items_df["id"],
        "分类": items_df["category"],
        "耗材名称": items_df["name"],
        "规格/型号": items_df["specification"],
        "品牌": items_df["brand"],
        "基础单位": items_df["base_unit"],
        "包装单位": items_df["package_unit"],
        "每包装数量": items_df["units_per_package"],
        "最低库存": items_df["minimum_quantity"],
        "当前库存": items_df["current_quantity"],
        "启用": items_df["is_active"],
    })


def _build_updates(original, edited):
    original_by_id = original.set_index("id").to_dict("index")
    updates = []
    for row in edited.to_dict("records"):
        item_id = row["_id"]
        values = {
            "category": _required(row["分类"], "分类"),
            "name": _required(row["耗材名称"], "耗材名称"),
            "specification": _text(row["规格/型号"]),
            "brand": _text(row["品牌"]),
            "base_unit": _required(row["基础单位"], "基础单位"),
            "package_unit": _text(row["包装单位"]) or None,
            "units_per_package": _number(row["每包装数量"]),
            "minimum_quantity": _number(row["最低库存"]),
            "is_active": bool(row["启用"]),
        }
        if bool(values["package_unit"]) != bool(values["units_per_package"]):
            raise ValueError(
                f"{values['name']} 的包装单位和每包装数量必须同时填写。"
            )
        old = original_by_id[item_id]
        if any(not _same(old.get(key), value) for key, value in values.items()):
            values["updated_at"] = datetime.now(ZoneInfo("UTC")).isoformat()
            updates.append((item_id, values))
    return updates


def _required(value, label):
    result = _text(value)
    if not result:
        raise ValueError(f"{label}不能为空。")
    return result


def _text(value):
    return "" if pd.isna(value) else str(value).strip()


def _number(value):
    result = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(result) else float(result)


def _same(left, right):
    if pd.isna(left) and right is None:
        return True
    return left == right
