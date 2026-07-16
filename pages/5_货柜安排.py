from importlib import reload

from utils.page_layout import configure_page


configure_page()

import db.inventory.container.progress as container_progress
import db.inventory.container.packaging as container_packaging
from db.supabase_client import supabase
from ui.inventory.container import events, form, page, tables
from ui.inventory.shared import filters
from utils.auth import require_page_access


require_page_access("container")
container_packaging = reload(container_packaging)
container_progress = reload(container_progress)
events = reload(events)
form = reload(form)
tables = reload(tables)
filters = reload(filters)
page = reload(page)
page.render_inventory_container_page(supabase)
