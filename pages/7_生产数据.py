from utils.page_layout import configure_page


configure_page()

from ui.production_data import render_production_data_page
from utils.auth import require_page_access


require_page_access("production_data")
render_production_data_page()
