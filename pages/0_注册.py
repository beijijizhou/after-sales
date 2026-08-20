from utils.page_layout import configure_page


configure_page()

from db.supabase_client import supabase
from ui.people import render_people_management_page
from utils.auth import require_page_access

require_page_access("register")
render_people_management_page(supabase)
