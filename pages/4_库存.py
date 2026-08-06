from importlib import reload

from utils.page_layout import configure_page


configure_page()

from db.supabase_client import supabase
import automation.production_reference as production_reference
import ui.inventory.page_tabs as inventory_page_tabs
import ui.inventory.summary as inventory_summary
import ui.inventory.stock.incoming as inventory_incoming
from utils.auth import require_page_access


require_page_access("inventory")
production_reference = reload(production_reference)
inventory_incoming = reload(inventory_incoming)
inventory_page_tabs = reload(inventory_page_tabs)
inventory_summary = reload(inventory_summary)
inventory_summary.render_inventory_summary(supabase)
