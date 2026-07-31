import pandas as pd
import streamlit as st

from db.inventory.container.editor import update_container_items
from utils.auth import get_current_operator_name


DISPLAY_COLUMNS = {
    "id": "记录ID", "expected_arrival_date": "预计到货日期",
    "category": "品类", "brand": "品牌", "material": "材质",
    "color": "颜色", "size": "型号", "quantity": "数量",
    "unit_cost": "成本", "note": "备注",
}


def render_container_item_editor(supabase, target, container_key, can_edit):
    if not can_edit:
        return
    source = target[list(DISPLAY_COLUMNS)].rename(columns=DISPLAY_COLUMNS).copy()
    source["预计到货日期"] = pd.to_datetime(
        source["预计到货日期"], errors="coerce"
    ).dt.date
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
