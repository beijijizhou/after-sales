from db.supabase_client import supabase
from ui.production_summary import render_production_summary
from utils.utility import get_selected_date


selected_date = get_selected_date()

render_production_summary(
    supabase=supabase,
    selected_date=selected_date,
    title="烫印",
    user_column="hotstamp_by",
)
