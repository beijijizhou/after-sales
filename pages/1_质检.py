from db.supabase_client import supabase
from ui.production_summary import render_production_summary
from utils.auth import require_page_access
from utils.utility import get_selected_date

require_page_access("qa")

selected_date = get_selected_date()

render_production_summary(
    supabase=supabase,
    selected_date=selected_date,
    title="质检",
    user_column="scanned_by",
)
