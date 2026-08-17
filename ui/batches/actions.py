"""One confirmation and feedback flow for domain batch reversals."""

import streamlit as st

from db.batches import BatchReference, reverse_batch
from utils.auth import get_current_operator_name


def render_batch_reversal_action(
    supabase,
    reference: BatchReference,
    *,
    key_scope,
    confirmation_label,
    button_label,
    success_state_key,
    success_message,
    error_label="撤销失败",
    button_type="secondary",
):
    """Render and execute one append-only, auditable batch reversal."""
    confirmed = st.checkbox(
        confirmation_label,
        key=f"batch_reversal_confirm_{key_scope}_{reference.batch_id}",
    )
    if not st.button(
        button_label,
        disabled=not confirmed,
        width="stretch",
        type=button_type,
        key=f"batch_reversal_button_{key_scope}_{reference.batch_id}",
    ):
        return False
    try:
        reverse_batch(
            supabase, reference, get_current_operator_name()
        )
    except Exception as error:
        st.error(f"{error_label}：{error}")
        return False
    st.session_state[success_state_key] = success_message
    st.rerun()
    return True
