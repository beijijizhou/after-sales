from utils.page_layout import configure_page


configure_page()

from db.supabase_client import supabase
from ui.access import render_access_management_page
from utils.auth import require_page_access


require_page_access("access_management")
render_access_management_page(supabase)
