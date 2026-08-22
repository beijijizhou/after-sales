"""Page orchestration for the after-sales hotstamp film workspace."""

import streamlit as st

from ui.after_sales_hotstamp.audit_view import (
    render_audit_view,
    render_batch_history,
)
from ui.after_sales_hotstamp.sync_view import render_sync_view
from utils.auth import has_role
from utils.auth.constants import ROLE_AFTER_SALES


def render_hotstamp_film_audit(supabase, folder_id):
    if not has_role(ROLE_AFTER_SALES):
        st.error("此功能仅对售后和管理员角色开放。")
        return
    st.title("人工登记分析")
    audit_tab, sync_tab, history_tab = st.tabs([
        "核对看板", "同步 Google 表格", "同步批次",
    ])
    with audit_tab:
        render_audit_view(supabase)
    with sync_tab:
        render_sync_view(supabase, folder_id)
    with history_tab:
        render_batch_history(supabase)
