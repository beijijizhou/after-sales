from importlib import reload

from db.supabase_client import supabase
import ui.inventory_container as inventory_container


inventory_container = reload(inventory_container)
inventory_container.render_inventory_container_page(supabase)
