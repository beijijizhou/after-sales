from importlib import reload

from db.supabase_client import supabase
import ui.inventory_container as inventory_container
from utils.auth import require_page_access


require_page_access("container")
inventory_container = reload(inventory_container)
inventory_container.render_inventory_container_page(supabase)
