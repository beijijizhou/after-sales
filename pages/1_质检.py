from datetime import datetime

from utils.page_layout import configure_page


configure_page()

from db.supabase_client import supabase
from ui.production.summary import render_production_summary
from utils.auth import require_page_access
from utils.production.constants import NY_TIMEZONE

require_page_access("qa")

render_production_summary(
    supabase=supabase,
    selected_date=datetime.now(NY_TIMEZONE).date(),
    title="质检",
    user_column="scanned_by",
)
