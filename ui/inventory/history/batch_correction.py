"""User-facing audited quantity correction for inventory movement batches."""

import pandas as pd
import streamlit as st

from db.batches import (
    InboundBatchKind,
    InboundBatchReference,
    InventoryQuantityCorrection,
    replace_inbound_batch,
)
from db.inventory.operations.batch_corrections import (
    build_batch_correction_adjustments,
    build_batch_correction_editor,
)
from db.inventory.operations.outbound_audit import load_outbound_inventory
from ui.inventory.operations.adjustment_preview import (
    build_inventory_change_comparison,
    render_inventory_change_comparison,
)
from ui.table_layout import fit_table_height
from utils.auth import get_current_operator_name, has_permission


def render_inventory_batch_correction(supabase, selected, batch_id):
    if selected.empty or not has_permission("can_edit_inventory"):
        return
    if selected.get("reversal_of_batch_id", pd.Series(dtype=object)).notna().any():
        return
    try:
        original = build_batch_correction_editor(selected)
    except ValueError as error:
        st.caption(str(error))
        return
    if original.empty:
        return
    st.divider()
    st.markdown("#### 校准批次数量")
    st.caption(
        "用于箱规、抄写或汇总数量算错的情况。系统保留原批次，"
        "并只生成差额更正流水；不会覆盖或删除历史。"
    )
    edited = st.data_editor(
        original,
        hide_index=True,
        width="stretch",
        height=fit_table_height(original),
        disabled=[
            "品牌", "材质", "颜色", "尺码", "原批次数量", "原单位成本",
        ],
        column_config={
            "校准后数量": st.column_config.NumberColumn(
                "校准后数量", min_value=0, step=1, format="%d",
            ),
            "原单位成本": st.column_config.NumberColumn(
                "原单位成本", format="$%.4f",
            ),
        },
        key=f"inventory_batch_correction_editor_{batch_id}",
    )
    try:
        adjustments = build_batch_correction_adjustments(
            selected, edited, batch_id
        )
    except ValueError as error:
        st.error(str(error))
        return
    original_total = int(original["原批次数量"].sum())
    corrected_total = int(pd.to_numeric(
        edited["校准后数量"], errors="coerce"
    ).fillna(0).sum())
    metrics = st.columns(3)
    metrics[0].metric("原批次数量", f"{original_total:,}")
    metrics[1].metric("校准后数量", f"{corrected_total:,}")
    metrics[2].metric("批次差额", f"{corrected_total - original_total:+,}")
    if adjustments.empty:
        st.info("修改“校准后数量”后，这里会显示库存变化核对。")
        return
    first = selected.iloc[0]
    try:
        current = load_outbound_inventory(
            supabase, first["department"], first["category"]
        )
        review = build_inventory_change_comparison(
            current.assign(
                department=first["department"], category=first["category"]
            ),
            adjustments.assign(
                部门=first["department"], 品类=first["category"]
            ),
        )
    except Exception as error:
        st.error(f"校准前库存核对失败：{error}")
        return
    render_inventory_change_comparison(review, title="校准后库存核对")
    has_negative = pd.to_numeric(
        review.get("调整后库存"), errors="coerce"
    ).fillna(0).lt(0).any()
    if has_negative:
        st.error("校准会产生负库存，请先核对数量。")
    confirmed = st.checkbox(
        "我已核对原批次、校准数量和调整后库存",
        key=f"confirm_inventory_batch_correction_{batch_id}",
    )
    if not st.button(
        "保存批次校准", type="primary", width="stretch",
        disabled=not confirmed or has_negative,
        key=f"save_inventory_batch_correction_{batch_id}",
    ):
        return
    try:
        correction_id = replace_inbound_batch(
            supabase,
            InboundBatchReference(
                InboundBatchKind.INVENTORY_MOVEMENT,
                batch_id,
                first["department"],
                first["category"],
            ),
            InventoryQuantityCorrection(adjustments),
            get_current_operator_name(),
        )
    except Exception as error:
        st.error(f"批次校准失败：{error}")
        return
    st.session_state["inventory_saved_message"] = (
        f"批次校准已保存：{original_total:,} → {corrected_total:,}｜"
        f"更正批次 {correction_id}"
    )
    st.rerun()
