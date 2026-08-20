import streamlit as st

from db.inventory.container.workflow import (
    get_container_undo_kind,
    undo_latest_container_confirmation,
)
from utils.auth import get_current_operator_name, has_permission
from ui.inventory.container.posting import (
    render_container_inventory_change_review,
)


def render_container_undo_action(
    supabase, target_df, container_key, key_prefix, embedded=False,
):
    if target_df.empty or "status" not in target_df.columns:
        return
    statuses = set(
        target_df["status"].fillna("").astype(str).str.strip()
    ) - {""}
    if len(statuses) != 1:
        return
    kind = get_container_undo_kind(next(iter(statuses)))
    if not kind:
        return
    if not has_permission("can_edit_container"):
        return

    container_no = target_df.get("container_no")
    label = container_key
    if container_no is not None:
        values = container_no.dropna().astype(str).str.strip()
        if not values.empty and values.iloc[0]:
            label = values.iloc[0]
    title = "撤销入库确认" if kind == "posting" else "撤销到柜确认"
    effect = (
        "系统会生成反向库存流水，货柜恢复为“已到柜”；"
        "原入库和撤销记录都会保留。若当时使用了“到柜并直接入库”，"
        "完成后还可以继续撤销到柜确认。"
        if kind == "posting"
        else "货柜恢复到确认前状态，并清除实际到柜日期；"
        "原确认和撤销记录都会保留。"
    )
    if embedded:
        embedded_title = (
            "撤销整笔入库" if kind == "posting" else "撤销到柜"
        )
        st.markdown(f"#### {embedded_title}")
        _render_undo_workflow(
            supabase, target_df, container_key, key_prefix, embedded_title,
            label, effect, kind,
        )
        return
    with st.expander(title, expanded=False):
        _render_undo_workflow(
            supabase, target_df, container_key, key_prefix, title,
            label, effect, kind,
        )


def _render_undo_workflow(
    supabase, target_df, container_key, key_prefix, title, label, effect, kind,
):
    if kind == "posting":
        st.caption(
            "库存核对与“库存管理 → 批次修改与撤销”使用同一套"
            "当前库存、本次出库和撤销后库存口径。"
        )
        render_container_inventory_change_review(
            supabase, target_df, "扣减", "撤销入库后的库存核对"
        )
    _render_undo_controls(
        supabase, container_key, key_prefix, title, label, effect
    )


def _render_undo_controls(
    supabase, container_key, key_prefix, title, label, effect,
):
    st.warning(f"{label}｜{effect}")
    note = st.text_input(
        "撤销原因（可选）",
        key=f"{key_prefix}_undo_note_{container_key}",
    )
    confirmed = st.checkbox(
        f"我确认要{title}：{label}",
        key=f"{key_prefix}_undo_confirm_{container_key}",
    )
    if not st.button(
        title,
        width="stretch",
        type="primary",
        disabled=not confirmed,
        key=f"{key_prefix}_undo_button_{container_key}",
    ):
        return
    try:
        result = undo_latest_container_confirmation(
            supabase,
            container_key,
            get_current_operator_name(),
            note,
        )
    except Exception as error:
        st.error(f"{title}失败：{error}")
        return
    st.session_state["container_undo_saved"] = (
        f"{label} 已完成{title}，当前状态：{result['status']}"
    )
    if result.get("kind") == "posting":
        st.session_state["inventory_saved_message"] = (
            f"{label} 的入库批次已撤销；库存管理已同步生成反向流水，"
            "当前库存已恢复。"
        )
    st.rerun()
