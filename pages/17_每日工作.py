from utils.page_layout import configure_page


configure_page()

from db.supabase_client import supabase
from ui.daily_work import render_daily_work_page
from utils.auth import require_page_access


require_page_access("daily_work")
render_daily_work_page(supabase)
