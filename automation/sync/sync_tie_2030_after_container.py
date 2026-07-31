from datetime import date

from automation.sync.uv_sheet_inventory import (
    InventorySku,
    sync_usage_to_inventory,
)
from db.supabase_client import supabase


SKU = InventorySku(
    "UV", "铁板画", "", "铁牌", "白", "2030"
)
DAILY_USAGE = {
    date(2026, 7, 29): 1_996,
    date(2026, 7, 30): 2_608,
}


if __name__ == "__main__":
    imported, skipped = sync_usage_to_inventory(
        supabase,
        SKU,
        DAILY_USAGE,
        created_by="Andy",
        reason_product_code="Tie_2030",
    )
    print({
        "imported": imported,
        "skipped": skipped,
        "total": sum(DAILY_USAGE.values()),
    })
