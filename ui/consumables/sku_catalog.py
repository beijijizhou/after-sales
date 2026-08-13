"""Consumable SKU catalog editor."""

import streamlit as st

from db.consumables import update_consumable_item
from ui.consumables.sku_models import EDIT_COLUMNS, build_editor, build_updates


def render_catalog(supabase, items, can_manage):
    st.subheader("现有耗材 SKU")
    if items.empty:
        st.info("当前部门还没有耗材 SKU。")
        return
    edited = st.data_editor(build_editor(items), width="stretch", hide_index=True, disabled=["_id", "包装单位", "当前库存（箱）"] if can_manage else ["_id", *EDIT_COLUMNS], key="consumable_sku_catalog", column_config={
        "_id": None,
        "每箱数量": st.column_config.NumberColumn(min_value=0.0001, step=0.1, format="%.4f"),
        "最低库存（箱）": st.column_config.NumberColumn(min_value=0.0, step=1, format="%.2f"),
        "当前库存（箱）": st.column_config.NumberColumn(format="%.2f"),
    })
    if not can_manage:
        return
    st.caption("耗材统一按箱计数；当前库存请通过入库、领用或库存修正处理。")
    if not st.button("保存 SKU 修改", width="stretch"):
        return
    try:
        updates = build_updates(items, edited)
        for item_id, values in updates:
            update_consumable_item(supabase, item_id, values)
    except Exception as error:
        st.error(f"保存 SKU 失败：{error}")
        return
    if not updates:
        st.info("SKU 信息没有变化。")
        return
    st.session_state["consumable_saved_message"] = f"已保存 {len(updates)} 个耗材 SKU 的修改。"
    st.rerun()
