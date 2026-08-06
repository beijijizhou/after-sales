from utils.page_layout import configure_page


configure_page()

import streamlit as st

from db.supabase_client import supabase
from ui.inventory.dashboard import render_inventory_dashboard
from utils.auth import require_page_access


require_page_access("inventory_dashboard")

saved_message = st.session_state.pop(
    "inventory_dashboard_saved_message", None
)
error_message = st.session_state.pop(
    "inventory_dashboard_error_message", None
)
if saved_message:
    st.success(saved_message)
if error_message:
    st.error(error_message)
render_inventory_dashboard(supabase)
