from datetime import date

from automation.sync.uv_sheet_inventory import (
    InventorySku,
    sync_usage_to_inventory,
)
from db.supabase_client import supabase


DAILY_USAGE = {
    date(2026, 5, 1): 52, date(2026, 5, 3): 72,
    date(2026, 5, 4): 13, date(2026, 5, 6): 60,
    date(2026, 5, 7): 21, date(2026, 5, 8): 51,
    date(2026, 5, 9): 18, date(2026, 5, 10): 17,
    date(2026, 5, 11): 50, date(2026, 5, 12): 33,
    date(2026, 5, 13): 19, date(2026, 5, 14): 34,
    date(2026, 5, 15): 12, date(2026, 5, 16): 17,
    date(2026, 5, 17): 17, date(2026, 5, 18): 25,
    date(2026, 5, 19): 56, date(2026, 5, 20): 27,
    date(2026, 5, 21): 42, date(2026, 5, 22): 33,
    date(2026, 5, 23): 16, date(2026, 5, 24): 14,
    date(2026, 5, 25): 54, date(2026, 5, 27): 37,
    date(2026, 5, 29): 30, date(2026, 6, 1): 73,
    date(2026, 6, 5): 44, date(2026, 6, 6): 18,
    date(2026, 6, 7): 14, date(2026, 6, 8): 138,
    date(2026, 6, 9): 27, date(2026, 6, 10): 31,
    date(2026, 6, 11): 63, date(2026, 6, 15): 101,
    date(2026, 6, 16): 46, date(2026, 6, 17): 29,
    date(2026, 6, 18): 24, date(2026, 6, 19): 49,
    date(2026, 6, 20): 61, date(2026, 6, 22): 97,
    date(2026, 6, 25): 39, date(2026, 6, 26): 31,
    date(2026, 6, 27): 26, date(2026, 6, 28): 36,
    date(2026, 6, 29): 71, date(2026, 7, 1): 189,
    date(2026, 7, 2): 66, date(2026, 7, 3): 61,
    date(2026, 7, 5): 45, date(2026, 7, 6): 110,
    date(2026, 7, 7): 72, date(2026, 7, 8): 65,
    date(2026, 7, 9): 12, date(2026, 7, 10): 182,
    date(2026, 7, 12): 38, date(2026, 7, 13): 168,
    date(2026, 7, 14): 107, date(2026, 7, 15): 89,
    date(2026, 7, 20): 103, date(2026, 7, 21): 124,
    date(2026, 7, 22): 59, date(2026, 7, 23): 69,
    date(2026, 7, 24): 75, date(2026, 7, 25): 14,
    date(2026, 7, 26): 47, date(2026, 7, 27): 162,
    date(2026, 7, 28): 118, date(2026, 7, 29): 59,
    date(2026, 7, 30): 45,
}

SKU = InventorySku(
    department="UV",
    category="铁板画",
    brand="",
    material="铁牌",
    color="白",
    size="1530",
)


if __name__ == "__main__":
    imported, skipped = sync_usage_to_inventory(
        supabase,
        SKU,
        DAILY_USAGE,
        created_by="Andy",
        reason_product_code="CHEPAI",
    )
    print({
        "imported_days": len(imported),
        "imported_quantity": sum(imported.values()),
        "skipped_days": len(skipped),
        "skipped_quantity": sum(skipped.values()),
    })
