from utils.page_layout import configure_page


configure_page()

from db.supabase_client import supabase
from ui.inventory.sku.standalone import render_sku_management_page
from utils.auth import require_page_access


require_page_access("sku_management")
render_sku_management_page(supabase)
