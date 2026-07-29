from importlib import reload

from utils.page_layout import configure_page


configure_page()

import streamlit as st

from db.supabase_client import supabase
import ui.finance.cost_editor as finance_cost_editor
import ui.finance.page as finance_page
from utils.auth import is_admin, require_page_access


require_page_access("finance")
if not is_admin():
    st.error("财务页面仅管理员可以查看")
    st.stop()

try:
    finance_cost_editor = reload(finance_cost_editor)
    finance_page = reload(finance_page)
    finance_page.render_finance_page(supabase)
except Exception as error:
    st.error(f"财务数据加载失败：{error}")
