from utils.page_layout import configure_page


configure_page()

from db.supabase_client import supabase
from ui.logistics import render_logistics_page
from utils.auth import require_page_access


require_page_access("logistics")
render_logistics_page(supabase)
