from importlib import reload

from utils.page_layout import configure_page


configure_page()

from db.supabase_client import supabase
import ui.inventory.summary as inventory_summary
from utils.auth import require_page_access


require_page_access("inventory")
inventory_summary = reload(inventory_summary)
inventory_summary.render_inventory_summary(supabase)
