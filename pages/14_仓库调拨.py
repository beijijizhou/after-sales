from utils.page_layout import configure_page


configure_page()

from db.supabase_client import supabase
from ui.inventory.transfers import render_warehouse_transfer_page
from utils.auth import require_page_access


require_page_access("inventory_transfer")
render_warehouse_transfer_page(supabase)
