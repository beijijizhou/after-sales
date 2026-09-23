"""User-facing audited quantity correction for inventory movement batches."""

import pandas as pd
import streamlit as st

from db.batches import (
    InboundCostCorrection,
    InboundBatchKind,
    InboundBatchReference,
    InventoryQuantityCorrection,
    replace_inbound_batch,
)
from db.finance import load_inventory_batch_cost_lots
from db.inventory.operations.batch_corrections import (
    attach_batch_cost_lots,
    build_batch_correction_adjustments,
    build_batch_correction_editor,
    find_batch_cost_changes,
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
    quantities = pd.to_numeric(
        selected.get("quantity_change"), errors="coerce"
    ).fillna(0)
    can_edit_cost = quantities.gt(0).all() and has_permission(
        "can_manage_cost"
    )
    if can_edit_cost:
        try:
            original = attach_batch_cost_lots(
                original,
                load_inventory_batch_cost_lots(supabase, batch_id),
            )
        except Exception as error:
            st.error(f"批次成本加载失败：{error}")
            return
    st.divider()
    st.markdown("#### 校准批次数量与成本")
    st.caption(
        "用于箱规、抄写或汇总数量算错的情况。系统保留原批次，"
        "数量只生成差额更正流水；入库价格会同步成本批次、库存流水"
        "和已发生的成本分摊。所有修改保留操作人和时间。"
    )
    disabled = [
        "品牌", "材质", "颜色", "尺码", "原批次数量", "原单位成本",
    ]
    if "校准后成本" in original and not can_edit_cost:
        disabled.append("校准后成本")
    column_config = {
        "校准后数量": st.column_config.NumberColumn(
            "校准后数量", min_value=0, step=1, format="%d",
        ),
        "原单位成本": st.column_config.NumberColumn(
            "原单位成本", format="$%.4f",
        ),
    }
    if "成本批次ID" in original:
        column_config["成本批次ID"] = None
    if "校准后成本" in original:
        column_config["校准后成本"] = st.column_config.NumberColumn(
            "校准后成本", min_value=0.0001, step=0.0001,
            format="$%.4f",
        )
    edited = st.data_editor(
        original,
        hide_index=True,
        width="stretch",
        height=fit_table_height(original),
        disabled=disabled,
        column_config=column_config,
        key=f"inventory_batch_correction_editor_{batch_id}",
    )
    try:
        adjustments = build_batch_correction_adjustments(
            selected, edited, batch_id
        )
        cost_changes = find_batch_cost_changes(original, edited)
    except ValueError as error:
        st.error(str(error))
        return
    original_total = int(original["原批次数量"].sum())
    corrected_total = int(pd.to_numeric(
        edited["校准后数量"], errors="coerce"
    ).fillna(0).sum())
    metrics = st.columns(4)
    metrics[0].metric("原批次数量", f"{original_total:,}")
    metrics[1].metric("校准后数量", f"{corrected_total:,}")
    metrics[2].metric("批次差额", f"{corrected_total - original_total:+,}")
    metrics[3].metric("价格修改", f"{len(cost_changes):,} SKU")
    if adjustments.empty and not cost_changes:
        hint = "修改“校准后数量”"
        if can_edit_cost:
            hint += "或“校准后成本”"
        st.info(f"{hint}后，这里会显示变更核对。")
        return
    first = selected.iloc[0]
    has_negative = False
    if not adjustments.empty:
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
    elif cost_changes:
        st.info("本次只修改批次价格，不改变当前库存数量。")
    if has_negative:
        st.error("校准会产生负库存，请先核对数量。")
    confirmed = st.checkbox(
        "我已核对原批次、校准数量、成本和调整后库存",
        key=f"confirm_inventory_batch_correction_{batch_id}",
    )
    if not st.button(
        "保存批次校准", type="primary", width="stretch",
        disabled=not confirmed or has_negative,
        key=f"save_inventory_batch_correction_{batch_id}",
    ):
        return
    try:
        operator = get_current_operator_name()
        for cost_lot_id, unit_cost in cost_changes:
            replace_inbound_batch(
                supabase,
                InboundBatchReference(
                    InboundBatchKind.INVENTORY_COST_LOT, cost_lot_id
                ),
                InboundCostCorrection(unit_cost),
                operator,
            )
        correction_id = None
        if not adjustments.empty:
            correction_id = replace_inbound_batch(
                supabase,
                InboundBatchReference(
                    InboundBatchKind.INVENTORY_MOVEMENT,
                    batch_id,
                    first["department"],
                    first["category"],
                ),
                InventoryQuantityCorrection(adjustments),
                operator,
            )
    except Exception as error:
        st.error(f"批次校准失败：{error}")
        return
    for key in list(st.session_state):
        if str(key).startswith("inventory_cost_history_data_"):
            st.session_state.pop(key, None)
    detail = f"数量 {original_total:,} → {corrected_total:,}"
    if cost_changes:
        detail += f"｜价格 {len(cost_changes)} SKU"
    if correction_id:
        detail += f"｜更正批次 {correction_id}"
    st.session_state["inventory_saved_message"] = f"批次校准已保存：{detail}"
    st.rerun()
