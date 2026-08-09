import pandas as pd
import streamlit as st

from db.inventory.container.editor import (
    correct_posted_container_quantities,
    update_container_items,
)
from utils.auth import get_current_operator_name
from utils.sku_sorting import sort_sku_rows
from ui.table_layout import fit_table_height
from ui.inventory.container.posting import (
    render_container_inventory_change_review,
)


DISPLAY_COLUMNS = {
    "id": "记录ID", "expected_arrival_date": "预计到货日期",
    "category": "品类", "brand": "品牌", "material": "材质",
    "color": "颜色", "size": "型号", "quantity": "数量",
    "unit_cost": "成本", "note": "备注",
}


def render_container_item_editor(supabase, target, container_key, can_edit):
    if not can_edit:
        return
    statuses = set(target["status"].fillna("").astype(str))
    if statuses == {"已入库"}:
        render_posted_container_correction(
            supabase, target, container_key
        )
        return
    source = build_container_item_editor_source(target)
    st.subheader("修改货柜明细")
    edited = st.data_editor(
        source, hide_index=True, width="stretch",
        disabled=["记录ID"], key=f"container_item_editor_{container_key}",
        column_config={
            "记录ID": None,
            "预计到货日期": st.column_config.DateColumn(),
            "数量": st.column_config.NumberColumn(min_value=0, step=1),
            "成本": st.column_config.NumberColumn(min_value=0.0, step=0.0001, format="%.4f"),
        },
        height=fit_table_height(source),
    )
    if st.button("保存货柜明细修改", type="primary", key=f"save_container_items_{container_key}"):
        updates = {}
        reverse = {value: key for key, value in DISPLAY_COLUMNS.items()}
        for row in edited.to_dict("records"):
            item_id = str(row.pop("记录ID"))
            values = {reverse[key]: value for key, value in row.items()}
            values["expected_arrival_date"] = values["expected_arrival_date"].isoformat()
            updates[item_id] = values
        try:
            result = update_container_items(
                supabase, container_key, updates, get_current_operator_name()
            )
            st.success(f"已保存 {result['rows']} 行修改")
            st.rerun()
        except Exception as error:
            st.error(f"货柜明细保存失败：{error}")


def render_posted_container_correction(supabase, target, container_key):
    st.subheader("更正已入库货柜明细")
    st.caption(
        "保存后会保留原入库流水，并生成独立的货柜更正流水；"
        "已被消耗、无法再次扣减的差额会明确记录，不会扣成负库存。"
    )
    source = build_container_item_editor_source(target)
    edited = st.data_editor(
        source, hide_index=True, width="stretch",
        disabled=[column for column in source.columns if column != "数量"],
        key=f"posted_container_item_editor_{container_key}",
        column_config={
            "记录ID": None,
            "预计到货日期": st.column_config.DateColumn(),
            "数量": st.column_config.NumberColumn(min_value=0, step=1),
            "成本": st.column_config.NumberColumn(format="%.4f"),
        },
        height=fit_table_height(source),
    )
    original = source.set_index("记录ID")["数量"].astype(int)
    revised = edited.set_index("记录ID")["数量"].astype(int)
    changed = revised[revised != original]
    if changed.empty:
        st.info("修改数量后，这里会显示更正汇总。")
        return
    difference = int(changed.sum() - original.loc[changed.index].sum())
    st.metric("货柜数量变化", f"{difference:+,} 件")
    correction_rows = target[
        target["id"].astype(str).isin(changed.index.astype(str))
    ].copy()
    revised_by_id = {str(key): int(value) for key, value in changed.items()}
    correction_rows["_revised_quantity"] = correction_rows["id"].astype(
        str
    ).map(revised_by_id)
    quantity_difference = (
        correction_rows["_revised_quantity"].astype(int)
        - pd.to_numeric(
            correction_rows["quantity"], errors="coerce"
        ).fillna(0).astype(int)
    )
    correction_rows["操作"] = quantity_difference.map(
        lambda value: "增加" if value > 0 else "扣减"
    )
    correction_rows["quantity"] = quantity_difference.abs()
    render_container_inventory_change_review(
        supabase, correction_rows, None, "更正后的库存核对"
    )
    confirmed = st.checkbox(
        "我已核对修正数量，并确认同步库存与保留更正流水",
        key=f"confirm_posted_container_correction_{container_key}",
    )
    if not st.button(
        "保存入库后更正", type="primary", width="stretch",
        disabled=not confirmed,
        key=f"save_posted_container_correction_{container_key}",
    ):
        return
    try:
        result = correct_posted_container_quantities(
            supabase, container_key,
            {str(key): int(value) for key, value in changed.items()},
            get_current_operator_name(),
        )
    except Exception as error:
        st.error(f"已入库货柜更正失败：{error}")
        return
    st.session_state["container_saved_message"] = (
        f"已更正 {result['rows']} 行；库存同步 "
        f"{result['inventory_change']:+,} 件；"
        f"已消耗历史差额 {result['unresolved_shortage']:,} 件"
    )
    st.rerun()


def build_container_item_editor_source(target):
    source = target[list(DISPLAY_COLUMNS)].rename(columns=DISPLAY_COLUMNS).copy()
    source["预计到货日期"] = pd.to_datetime(
        source["预计到货日期"], errors="coerce"
    ).dt.date
    return sort_sku_rows(
        source,
        material="材质", color="颜色", size="型号",
        leading=["材质", "品牌"],
    )
