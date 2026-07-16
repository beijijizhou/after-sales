from utils.page_layout import configure_page


configure_page()

from db.supabase_client import supabase
from ui.platform_summary import render_platform_summary
from utils.auth import require_page_access
from utils.utility import get_selected_date

require_page_access("platform")

selected_date = get_selected_date()

render_platform_summary(
    supabase=supabase,
    selected_date=selected_date,
)
