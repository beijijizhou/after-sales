"""Inventory movement selection and audited correction/reversal workflow."""

import pandas as pd
import streamlit as st

from db.inventory.container.repository import (
    load_posted_container_by_inventory_batch,
)
from db.inventory.operations.adjustments import reverse_inventory_batch
from db.inventory.operations.outbound_audit import load_outbound_inventory
from ui.inventory.container.item_editor import (
    render_posted_container_correction,
)
from ui.inventory.history.core.batches import add_movement_batch_key
from ui.inventory.history.core.tables import render_movement_table
from ui.inventory.history.workflows.daily_outbound import (
    is_editable_daily_outbound,
    movement_rows_as_adjustments,
    render_daily_outbound_replacement,
)
from ui.inventory.i18n import t
from ui.inventory.operations.adjustment_preview import (
    build_inventory_change_comparison,
    render_inventory_change_comparison,
)
from utils.auth import get_current_operator_name, has_permission


def render_selected_movement(
    supabase, dated_movement_df, selected_batch, allow_undo=True,
    visible_sizes=None,
):
    movements = add_movement_batch_key(dated_movement_df)
    selected = movements[movements["batch_key"] == selected_batch]
    render_movement_table(
        selected, visible_sizes,
        key=f"inventory_movement_detail_{selected_batch}",
    )
    reversed_ids = set()
    if "reversal_of_batch_id" in movements.columns:
        reversed_ids = set(
            movements["reversal_of_batch_id"].dropna().astype(str)
        )
    if allow_undo:
        render_movement_undo(supabase, selected, reversed_ids)
    else:
        render_container_batch_correction(supabase, selected)


def render_container_batch_correction(supabase, selected):
    if selected.empty or not has_permission("can_edit_inventory"):
        return
    if not selected["quantity_change"].gt(0).all():
        return
    batch_ids = selected.get("batch_id", pd.Series(dtype=str)).dropna(
    ).astype(str).unique()
    if len(batch_ids) != 1:
        return
    try:
        target = load_posted_container_by_inventory_batch(
            supabase, batch_ids[0]
        )
    except Exception as error:
        st.caption(f"货柜批次更正入口暂时无法加载：{error}")
        return
    target = pd.DataFrame(target)
    if target.empty:
        return
    st.divider()
    render_posted_container_correction(
        supabase, target, str(target.iloc[0]["container_key"])
    )


def render_movement_undo(supabase, selected, reversed_ids):
    if selected.empty or not has_permission("can_edit_inventory"):
        return
    if "batch_id" not in selected or selected["batch_id"].isna().all():
        st.caption(t("运行最新版库存 SQL 后，才可以撤销这笔旧记录。"))
        return
    batch_ids = selected["batch_id"].dropna().astype(str).unique()
    if len(batch_ids) > 1:
        st.caption("旧版自动消耗记录由多个批次合并展示，不能使用单批次撤销。")
        return
    if "reversal_of_batch_id" in selected and selected[
        "reversal_of_batch_id"
    ].notna().any():
        st.caption(t("这是撤销记录，不能再次撤销。"))
        return
    batch_id = batch_ids[0]
    if batch_id in reversed_ids:
        st.success(t("这笔库存变动已撤销"))
        return
    if is_editable_daily_outbound(selected):
        action = st.segmented_control(
            "处理方式", ["修改并替换", "仅撤销"], default="修改并替换",
            key=f"inventory_batch_action_{batch_id}",
        )
        if action == "修改并替换":
            render_daily_outbound_replacement(supabase, batch_id)
            return
    _render_reversal_stock_review(supabase, selected)
    confirmed = st.checkbox(
        t("我确认撤销这笔库存变动"),
        key=f"confirm_inventory_undo_{batch_id}",
    )
    if not st.button(
        t("撤销这笔库存变动"), disabled=not confirmed, width="stretch"
    ):
        return
    row = selected.iloc[0]
    try:
        reverse_inventory_batch(
            supabase, batch_id, row["department"], row["category"],
            get_current_operator_name(),
        )
    except Exception as error:
        st.error(f"{t('撤销失败')}: {error}")
        return
    st.session_state["inventory_saved_message"] = t(
        "库存变动已撤销，库存明细已恢复"
    )
    st.rerun()


def _render_reversal_stock_review(supabase, selected):
    row = selected.iloc[0]
    try:
        inventory = load_outbound_inventory(
            supabase, row["department"], row["category"]
        )
    except Exception as error:
        st.error(f"撤销前库存核对失败：{error}")
        return
    inventory["department"] = row["department"]
    inventory["category"] = row["category"]
    reversal = movement_rows_as_adjustments(selected, reverse=True)
    render_inventory_change_comparison(
        build_inventory_change_comparison(inventory, reversal),
        title="撤销后的库存核对",
    )
