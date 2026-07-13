import streamlit as st

from ui.barcode_operations_ui import (
    render_direct_operation_entry,
)
from ui.barcode_tracking_ui import render_operation_tracking_section
from utils.auth import can_access_page, render_navigation


render_navigation()

if not can_access_page("operation_tracking"):
    st.title("问题件追踪")
    st.info("请从左侧选择可以查看的页面。")
    st.stop()

st.title("问题件追踪")
render_direct_operation_entry()
render_operation_tracking_section()
