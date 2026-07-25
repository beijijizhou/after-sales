from utils.page_layout import configure_page


configure_page()

from ui.image_stretch import render_image_stretch_page
from utils.auth import require_page_access


require_page_access("image_stretch")
render_image_stretch_page()
