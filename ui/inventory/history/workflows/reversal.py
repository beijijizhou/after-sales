"""Inventory movement selection and audited correction/reversal workflow."""

import pandas as pd
import streamlit as st

from db.inventory.container.repository import (
    load_posted_container_by_inventory_batch,
)
from db.batches import BatchKind, BatchReference, reversed_record_ids
from db.inventory.operations.daily_outbound_versions import (
    load_daily_outbound_revision_by_inventory_batch,
)
from db.inventory.operations.outbound_audit import load_outbound_inventory
from ui.inventory.container.item_editor import (
    render_posted_container_correction,
)
from ui.inventory.container.reversal import render_container_undo_action
from ui.inventory.history.core.batches import add_movement_batch_key
from ui.inventory.history.core.tables import render_movement_table
from ui.inventory.history.workflows.daily_outbound import (
    is_editable_daily_outbound,
    movement_rows_as_adjustments,
    render_daily_outbound_replacement,
)
from ui.inventory.history.batch_correction import (
    render_inventory_batch_correction,
)
from ui.inventory.i18n import t
from ui.inventory.operations.adjustment_preview import (
    build_inventory_change_comparison,
    render_inventory_change_comparison,
)
from ui.batches import render_batch_reversal_action
from utils.auth import has_permission


def render_selected_movement(
    supabase, dated_movement_df, selected_batch, allow_undo=True,
    visible_sizes=None, key_scope="inventory_history",
):
    movements = add_movement_batch_key(dated_movement_df)
    selected = movements[movements["batch_key"] == selected_batch]
    render_movement_table(
        selected, visible_sizes,
        key=f"inventory_movement_detail_{key_scope}_{selected_batch}",
    )
    reversed_ids = reversed_record_ids(movements)
    container_target = load_container_batch_target(supabase, selected)
    if not container_target.empty:
        if allow_undo:
            render_container_batch_management(
                supabase, container_target, key_scope
            )
        else:
            st.info(
                "这是货柜入库批次。数量、成本和整批撤销请统一前往"
                "“批次修改与撤销”处理。"
            )
        return
    if allow_undo:
        render_movement_undo(
            supabase, selected, reversed_ids, key_scope=key_scope
        )
    else:
        render_selected_batch_correction(
            supabase, selected, reversed_ids, key_scope=key_scope
        )


def load_container_batch_target(supabase, selected):
    if selected.empty:
        return pd.DataFrame()
    if not selected["quantity_change"].gt(0).all():
        return pd.DataFrame()
    reasons = selected.get(
        "reason", pd.Series("", index=selected.index, dtype=str)
    ).fillna("").astype(str)
    if not reasons.str.startswith("货柜入库：").all():
        return pd.DataFrame()
    batch_ids = selected.get("batch_id", pd.Series(dtype=str)).dropna(
    ).astype(str).unique()
    if len(batch_ids) != 1:
        return pd.DataFrame()
    try:
        target = load_posted_container_by_inventory_batch(
            supabase, batch_ids[0]
        )
    except Exception as error:
        st.caption(f"货柜批次更正入口暂时无法加载：{error}")
        return pd.DataFrame()
    return pd.DataFrame(target)


def render_container_batch_management(supabase, target, key_scope):
    target = pd.DataFrame(target)
    if target.empty:
        return
    st.divider()
    container_key = str(target.iloc[0]["container_key"])
    statuses = set(
        target["status"].fillna("").astype(str).str.strip()
    )
    if statuses != {"已入库"}:
        st.success("这个货柜入库批次已经撤销，货柜与库存状态均已同步。")
        return
    st.markdown("#### 货柜入库批次维护")
    st.caption(
        "这里是已入库货柜的唯一修改入口；保存后会同时更新库存、"
        "成本、货柜明细和审计历史。"
    )
    can_correct = has_permission("can_edit_inventory")
    can_reverse = has_permission("can_edit_container")
    options = []
    if can_correct:
        options.append("修改数量与成本")
    if can_reverse:
        options.append("撤销整笔入库")
    if not options:
        st.info("当前账号可以查看这个货柜批次，但没有修改或撤销权限。")
        return
    action = st.segmented_control(
        "处理方式", options, default=options[0],
        key=f"container_batch_action_{key_scope}_{container_key}",
    ) or options[0]
    if action == "修改数量与成本":
        render_posted_container_correction(
            supabase, target, container_key
        )
        return
    render_container_undo_action(
        supabase, target, container_key,
        f"inventory_container_batch_{key_scope}", embedded=True,
    )


def render_selected_batch_correction(
    supabase, selected, reversed_ids, key_scope="inventory_history",
):
    if selected.empty or "batch_id" not in selected:
        return
    batch_ids = selected["batch_id"].dropna().astype(str).unique()
    if len(batch_ids) != 1 or batch_ids[0] in reversed_ids:
        return
    batch_id = batch_ids[0]
    if is_editable_daily_outbound(selected):
        render_daily_outbound_replacement(
            supabase, batch_id, key_scope=key_scope
        )
        return
    render_inventory_batch_correction(supabase, selected, batch_id)


def render_movement_undo(
    supabase, selected, reversed_ids, key_scope="inventory_history",
):
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
    daily_revision = None
    if is_editable_daily_outbound(selected):
        try:
            daily_revision = load_daily_outbound_revision_by_inventory_batch(
                supabase, batch_id
            )
        except Exception:
            daily_revision = None
        action = st.segmented_control(
            "处理方式", ["修改并替换", "仅撤销"], default="修改并替换",
            key=f"inventory_batch_action_{key_scope}_{batch_id}",
        )
        if action == "修改并替换":
            render_daily_outbound_replacement(
                supabase, batch_id, key_scope=key_scope
            )
            return
    _render_reversal_stock_review(supabase, selected)
    row = selected.iloc[0]
    if daily_revision:
        daily_batch = daily_revision.get(
            "inventory_daily_outbound_batches"
        ) or {}
        reference = BatchReference(
            BatchKind.DAILY_OUTBOUND,
            daily_revision["daily_outbound_batch_id"],
            daily_batch.get("department") or row["department"],
            daily_batch.get("category") or row["category"],
        )
    else:
        reference = BatchReference(
            BatchKind.INVENTORY, batch_id,
            row["department"], row["category"],
        )
    render_batch_reversal_action(
        supabase,
        reference,
        key_scope=f"inventory_{key_scope}",
        confirmation_label=t("我确认撤销这笔库存变动"),
        button_label=t("撤销这笔库存变动"),
        success_state_key="inventory_saved_message",
        success_message=t("库存变动已撤销，库存明细已恢复"),
        error_label=t("撤销失败"),
    )


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
