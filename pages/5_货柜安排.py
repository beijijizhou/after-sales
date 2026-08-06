from utils.page_layout import configure_page


configure_page()

from db.supabase_client import supabase
from ui.inventory.container import page
from utils.auth import require_page_access


require_page_access("container")
page.render_inventory_container_page(supabase)
