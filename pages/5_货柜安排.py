from importlib import reload

import db.inventory.container.progress as container_progress
from db.supabase_client import supabase
from ui.inventory.container import events, form, page, tables
from ui.inventory.shared import filters
from utils.auth import require_page_access


require_page_access("container")
container_progress = reload(container_progress)
events = reload(events)
form = reload(form)
tables = reload(tables)
filters = reload(filters)
page = reload(page)
page.render_inventory_container_page(supabase)
