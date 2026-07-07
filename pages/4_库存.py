from importlib import reload

from db.supabase_client import supabase
import ui.inventory_summary as inventory_summary


inventory_summary = reload(inventory_summary)
inventory_summary.render_inventory_summary(supabase)
