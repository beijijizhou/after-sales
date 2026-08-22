import streamlit as st

from utils.page_layout import configure_page


configure_page()

from db.supabase_client import supabase
from ui.after_sales_hotstamp import render_hotstamp_film_audit
from utils.auth import require_page_access


require_page_access("after_sales_manual_analysis")
render_hotstamp_film_audit(
    supabase,
    str(st.secrets.get("AFTER_SALES_HOTSTAMP_FOLDER_ID", "")).strip(),
)
