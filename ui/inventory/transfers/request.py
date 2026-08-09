import pandas as pd
import streamlit as st

from db.inventory.warehouses import create_transfer_request
from ui.inventory.shared.linked_sku_table import linked_sku_options
from utils.auth import get_current_operator_name


def render_restock_request(supabase, warehouses, items, balances, can_edit):
    st.subheader("创建断码补货任务")
    st.caption("这里只说明需要补哪些 SKU，不要求提前填写数量；找到货后再填实际发出数量。")
    if not can_edit:
        st.info("当前账号只能查看，不能创建补货任务。")
        return
    warehouse_codes = warehouses["code"].tolist()
    first, second = st.columns(2)
    source_label = first.selectbox(
        "可能的来源仓库", ["现场决定", *warehouse_codes],
        key="restock_source_warehouse",
    )
    target_default = warehouse_codes.index("25") if "25" in warehouse_codes else 0
    target = second.selectbox(
        "目标仓库", warehouse_codes, index=target_default,
        key="restock_target_warehouse",
    )
    selected_item = render_linked_inventory_item_selector(items, "restock_item")
    selected_key = "restock_selected_item_ids"
    st.session_state.setdefault(selected_key, [])
    if st.button("加入补货清单", width="stretch"):
        if selected_item and selected_item not in st.session_state[selected_key]:
            st.session_state[selected_key].append(selected_item)
            st.rerun()
    selected_ids = st.session_state[selected_key]
    if not selected_ids:
        st.info("通过上方联动选择器加入需要补货的断码 SKU。")
        return
    selected = items[items["id"].isin(selected_ids)].copy()
    selected = attach_warehouse_quantities(selected, balances).rename(columns={
        "department": "部门", "category": "品类", "material": "材质",
        "brand": "品牌", "color": "颜色", "size": "尺码",
    })
    selected["移除"] = False
    editor = st.data_editor(
        selected[[
            "id", "部门", "品类", "材质", "品牌", "颜色", "尺码",
            "25仓", "60仓", "70仓", "移除",
        ]],
        hide_index=True, width="stretch", key="restock_selected_editor",
        disabled=[
            "id", "部门", "品类", "材质", "品牌", "颜色", "尺码",
            "25仓", "60仓", "70仓",
        ],
        column_config={"id": None, "移除": st.column_config.CheckboxColumn("移除")},
    )
    remove_mask = editor["移除"].fillna(False).astype(bool)
    remaining_ids = editor.loc[~remove_mask, "id"].tolist()
    if remaining_ids != selected_ids:
        st.session_state[selected_key] = remaining_ids
        st.rerun()
    note = st.text_input(
        "补货说明（可选）", value="补齐断码", key="restock_request_note"
    )
    if st.button("创建补货任务", type="primary", width="stretch"):
        if source_label == target:
            st.error("来源仓库和目标仓库不能相同。")
            return
        create_transfer_request(
            supabase, "" if source_label == "现场决定" else source_label,
            target, remaining_ids, note, get_current_operator_name(),
        )
        st.session_state[selected_key] = []
        st.session_state["warehouse_transfer_saved"] = "断码补货任务已创建。"
        st.rerun()


def render_linked_inventory_item_selector(items, key_prefix):
    source = items.copy()
    department_options = sorted({
        str(value).strip() for value in source["department"].dropna()
        if str(value).strip()
    })
    if "DTF" in department_options:
        department_options.remove("DTF")
        department_options.insert(0, "DTF")
    department = required_selectbox(
        "部门", department_options, f"{key_prefix}_department"
    )
    source = source[source["department"] == department]
    category = required_selectbox(
        "品类", sorted({
            str(value).strip() for value in source["category"].dropna()
            if str(value).strip()
        }), f"{key_prefix}_category"
    )
    source = source[source["category"] == category]
    columns = st.columns(4)
    options = linked_sku_options(source)
    material = required_selectbox(
        "材质", options["materials"], f"{key_prefix}_material", columns[0]
    )
    options = linked_sku_options(source, material)
    brand = required_selectbox(
        "品牌", options["brands"] or [""],
        f"{key_prefix}_brand", columns[1]
    )
    options = linked_sku_options(source, material, brand or None)
    color = required_selectbox(
        "颜色", options["colors"] or [""],
        f"{key_prefix}_color", columns[2]
    )
    options = linked_sku_options(source, material, brand or None, color or None)
    size = required_selectbox(
        "尺码/型号", options["sizes"], f"{key_prefix}_size", columns[3]
    )
    matches = source[
        (source["material"].fillna("") == material)
        & (source["brand"].fillna("") == brand)
        & (source["color"].fillna("") == color)
        & (source["size"].fillna("") == size)
    ]
    return None if matches.empty else matches.iloc[0]["id"]


def required_selectbox(label, options, key, container=None):
    target = container if container is not None else st
    options = list(options)
    if not options:
        target.text_input(label, value="", disabled=True, key=f"{key}_empty")
        return ""
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[0]
    return target.selectbox(label, options, key=key)


def attach_warehouse_quantities(items, balances):
    result = items.copy()
    balance = pd.DataFrame(balances)
    if balance.empty:
        for code in ["25", "60", "70"]:
            result[f"{code}仓"] = 0
        return result
    pivot = balance.pivot_table(
        index="inventory_item_id", columns="warehouse_code",
        values="quantity", aggfunc="sum", fill_value=0,
    )
    for code in ["25", "60", "70"]:
        result[f"{code}仓"] = result["id"].map(
            pivot[code] if code in pivot else {}
        ).fillna(0).astype(int)
    return result
