"""Google Sheets import facade for the after-sales hotstamp film audit."""

from automation.sync.after_sales_hotstamp.service import (
    load_hotstamp_film_previews,
)

__all__ = ["load_hotstamp_film_previews"]
