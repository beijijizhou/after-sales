from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.consumables import create_consumable_item, update_consumable_item
from ui.consumables.units import boxes_to_base, to_boxes
from utils.auth import get_current_operator_name


EDIT_COLUMNS = [
    "分类", "耗材名称", "规格/型号", "品牌", "基础单位",
    "包装单位", "每箱数量", "最低库存（箱）", "当前库存（箱）", "启用",
]


def render_sku_management(
    supabase, department_id, items_df, can_manage
):
    st.subheader("SKU 管理")
    create_tab, catalog_tab = st.tabs(["新增 SKU", "现有 SKU"])
    with create_tab:
        _render_create_form(
            supabase, department_id, items_df, can_manage
        )
    with catalog_tab:
        _render_catalog(supabase, items_df, can_manage)


def _render_create_form(supabase, department_id, items_df, can_manage):
    st.subheader("新增耗材 SKU")
    if not can_manage:
        st.info("当前账号只有查看权限，不能新增耗材 SKU。")
        return

    copy_options, copy_labels = _copy_options(items_df)
    copy_source_id = st.selectbox(
        "复制现有耗材 SKU（可选）",
        copy_options,
        format_func=lambda value: copy_labels.get(value, "不复制，从空白新增"),
        key="consumable_sku_copy_source",
        help="复制后保留耗材名称和计数单位，只需修改规格、品牌和每箱数量。",
    )
    defaults = _copy_defaults(items_df, copy_source_id)
    if copy_source_id:
        st.caption(
            "已固定分类、耗材名称、基础单位和包装单位；"
            "请修改规格/型号、品牌及每箱数量。"
        )
    form_scope = str(copy_source_id or "blank")

    with st.form(f"create_consumable_sku_{form_scope}"):
        col1, col2 = st.columns(2)
        category = col1.text_input(
            "分类 *", value=defaults["category"], placeholder="例如：膜",
            disabled=bool(copy_source_id),
        )
        name = col2.text_input(
            "耗材名称 *", value=defaults["name"],
            placeholder="例如：DTF转印膜", disabled=bool(copy_source_id),
        )
        col1, col2 = st.columns(2)
        specification = col1.text_input(
            "规格/型号（可选）", value=defaults["specification"],
            placeholder="例如：200米/卷"
        )
        brand = col2.text_input("品牌（可选）", value=defaults["brand"])
        col1, col2 = st.columns(2)
        base_unit = col1.text_input(
            "基础单位 *", value=defaults["base_unit"],
            placeholder="瓶、卷、米", disabled=bool(copy_source_id),
        )
        minimum_boxes = col2.number_input(
            "最低库存（箱，可选）", min_value=0.0,
            value=defaults["minimum_boxes"],
            step=1.0, format="%.2f",
        )
        col1, col2 = st.columns(2)
        col1.text_input("计数单位", value="箱", disabled=True)
        units_per_package = col2.number_input(
            "每箱数量 *", min_value=0.0001,
            value=defaults["units_per_package"], step=0.1, format="%.4f",
        )
        submitted = st.form_submit_button(
            "新增耗材 SKU", type="primary", width="stretch"
        )

    if not submitted:
        return
    if not category.strip() or not name.strip() or not base_unit.strip():
        st.error("请填写所有带 * 的必填项目。")
        return
    minimum_quantity = (
        None if minimum_boxes is None
        else float(minimum_boxes) * float(units_per_package)
    )
    values = {
        "department_id": department_id,
        "category": category.strip(),
        "name": name.strip(),
        "specification": specification.strip(),
        "brand": brand.strip(),
        "base_unit": base_unit.strip(),
        "package_unit": "箱",
        "units_per_package": units_per_package,
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


def _copy_options(items_df):
    if items_df is None or items_df.empty:
        return [""], {"": "不复制，从空白新增"}
    labels = {"": "不复制，从空白新增"}
    for row in items_df.to_dict("records"):
        item_id = str(row["id"])
        parts = [
            row.get("category"), row.get("name"),
            row.get("specification"), row.get("brand"),
        ]
        labels[item_id] = "｜".join(
            str(value).strip() for value in parts
            if pd.notna(value) and str(value).strip()
        )
    return ["", *[key for key in labels if key]], labels


def _copy_defaults(items_df, source_id):
    defaults = {
        "category": "", "name": "", "specification": "", "brand": "",
        "base_unit": "", "units_per_package": 1.0,
        "minimum_boxes": None,
    }
    if not source_id or items_df is None or items_df.empty:
        return defaults
    matches = items_df[items_df["id"].astype(str) == str(source_id)]
    if matches.empty:
        return defaults
    row = matches.iloc[0]
    defaults.update({
        "category": _text(row.get("category")),
        "name": _text(row.get("name")),
        "specification": _text(row.get("specification")),
        "brand": _text(row.get("brand")),
        "base_unit": _text(row.get("base_unit")),
        "units_per_package": float(row.get("units_per_package") or 1),
        "minimum_boxes": to_boxes(row.get("minimum_quantity"), row),
    })
    return defaults


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
        disabled=["_id", "包装单位", "当前库存（箱）"]
        if can_manage else ["_id", *EDIT_COLUMNS],
        key="consumable_sku_catalog",
        column_config={
            "_id": None,
            "每箱数量": st.column_config.NumberColumn(
                min_value=0.0001, step=0.1, format="%.4f"
            ),
            "最低库存（箱）": st.column_config.NumberColumn(
                min_value=0.0, step=1, format="%.2f"
            ),
            "当前库存（箱）": st.column_config.NumberColumn(format="%.2f"),
        },
    )
    if not can_manage:
        return
    st.caption("耗材统一按箱计数；当前库存请通过入库、领用或库存修正处理。")
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
        "包装单位": "箱",
        "每箱数量": items_df["units_per_package"],
        "最低库存（箱）": items_df.apply(
            lambda row: to_boxes(row["minimum_quantity"], row), axis=1
        ),
        "当前库存（箱）": items_df.apply(
            lambda row: to_boxes(row["current_quantity"], row), axis=1
        ),
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
            "package_unit": "箱",
            "units_per_package": _number(row["每箱数量"]),
            "minimum_quantity": boxes_to_base(
                row["最低库存（箱）"],
                {"package_unit": "箱", "units_per_package": row["每箱数量"]},
            ),
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
