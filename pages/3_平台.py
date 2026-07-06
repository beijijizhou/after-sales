from db.supabase_client import supabase
from ui.platform_summary import render_platform_summary
from utils.utility import get_selected_date


selected_date = get_selected_date()

render_platform_summary(
    supabase=supabase,
    selected_date=selected_date,
)
