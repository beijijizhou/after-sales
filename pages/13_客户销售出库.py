from utils.page_layout import configure_page


configure_page()

from db.supabase_client import supabase
from ui.inventory.sales.standalone import render_customer_sales_page
from utils.auth import require_page_access


require_page_access("customer_sales")
render_customer_sales_page(supabase)
