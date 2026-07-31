from datetime import date
from uuid import NAMESPACE_URL, uuid5

import pandas as pd

from automation.sync.uv_sheet_inventory import (
    InventorySku,
    sync_usage_to_inventory,
)
from db.inventory.operations.adjustments import apply_adjustment_rows
from db.supabase_client import supabase


CLOCK_COUNT = 8_850
CLOCK_USAGE = {
    date(2026, 5, 2): 78, date(2026, 5, 3): 26,
    date(2026, 5, 4): 62, date(2026, 5, 5): 2,
    date(2026, 5, 6): 36, date(2026, 5, 7): 33,
    date(2026, 5, 8): 52, date(2026, 5, 9): 41,
    date(2026, 5, 10): 10, date(2026, 5, 11): 44,
    date(2026, 5, 12): 74, date(2026, 5, 13): 41,
    date(2026, 5, 14): 52, date(2026, 5, 15): 40,
    date(2026, 5, 16): 26, date(2026, 5, 17): 23,
    date(2026, 5, 18): 108, date(2026, 5, 19): 78,
    date(2026, 5, 20): 99, date(2026, 5, 21): 66,
    date(2026, 5, 22): 80, date(2026, 5, 23): 49,
    date(2026, 5, 24): 28, date(2026, 5, 25): 98,
    date(2026, 5, 27): 51, date(2026, 5, 29): 60,
    date(2026, 6, 1): 92, date(2026, 6, 5): 60,
    date(2026, 6, 6): 73, date(2026, 6, 7): 8,
    date(2026, 6, 8): 68, date(2026, 6, 9): 25,
    date(2026, 6, 10): 58, date(2026, 6, 11): 48,
    date(2026, 6, 15): 73, date(2026, 6, 16): 80,
    date(2026, 6, 17): 37, date(2026, 6, 18): 83,
    date(2026, 6, 19): 9, date(2026, 6, 20): 13,
    date(2026, 6, 22): 123, date(2026, 6, 25): 63,
    date(2026, 6, 26): 41, date(2026, 6, 27): 67,
    date(2026, 6, 28): 77, date(2026, 6, 29): 137,
    date(2026, 6, 30): 82, date(2026, 7, 1): 19,
    date(2026, 7, 2): 76, date(2026, 7, 3): 24,
    date(2026, 7, 5): 31, date(2026, 7, 6): 70,
    date(2026, 7, 7): 74, date(2026, 7, 8): 96,
    date(2026, 7, 9): 114, date(2026, 7, 10): 135,
    date(2026, 7, 12): 151, date(2026, 7, 13): 126,
    date(2026, 7, 14): 141, date(2026, 7, 15): 137,
    date(2026, 7, 20): 148, date(2026, 7, 21): 142,
    date(2026, 7, 22): 127, date(2026, 7, 23): 120,
    date(2026, 7, 24): 144, date(2026, 7, 25): 114,
    date(2026, 7, 26): 165, date(2026, 7, 27): 133,
    date(2026, 7, 28): 144, date(2026, 7, 29): 121,
    date(2026, 7, 30): 155,
}
CLOCK_SKU = InventorySku(
    "UV", "木板画", "", "挂钟", "白", "25"
)
YUAN_SKU = InventorySku(
    "UV", "铁板画", "", "铁牌", "白", "YUAN"
)


def reconcile():
    if _current(CLOCK_SKU) != 0 or _movement_count(CLOCK_SKU):
        raise ValueError("挂钟已有库存或流水，停止重复重建")
    opening = CLOCK_COUNT + sum(CLOCK_USAGE.values())
    _apply(
        CLOCK_SKU, date(2026, 5, 1), "增加", opening,
        "挂钟重建期初库存｜今日清点8850+历史消耗5381",
        "opening", "uv-clock-reconstructed-opening-2026-05-01",
    )
    imported, skipped = sync_usage_to_inventory(
        supabase, CLOCK_SKU, CLOCK_USAGE, "Andy", "Guazhong_2525"
    )
    yuan_before = _current(YUAN_SKU)
    _apply(
        YUAN_SKU, date(2026, 7, 30), "扣减",
        yuan_before - 34_200,
        "临时库存调整｜2026-07-30今日清点34200片",
        "transfer", "uv-yuan-stock-count-2026-07-30",
    )
    if _current(CLOCK_SKU) != CLOCK_COUNT:
        raise ValueError("挂钟保存后库存核验失败")
    if _current(YUAN_SKU) != 34_200:
        raise ValueError("圆铁保存后库存核验失败")
    return {
        "clock_opening": opening,
        "clock_usage": sum(CLOCK_USAGE.values()),
        "clock_current": _current(CLOCK_SKU),
        "clock_imported_days": len(imported),
        "clock_skipped_days": len(skipped),
        "yuan_before": yuan_before,
        "yuan_adjustment": yuan_before - 34_200,
        "yuan_current": _current(YUAN_SKU),
    }


def _apply(sku, movement_date, operation, quantity, reason, source, seed):
    apply_adjustment_rows(
        supabase, sku.department, sku.category,
        pd.DataFrame([{
            "日期": movement_date, "操作": operation,
            "品牌": sku.brand, "材质": sku.material,
            "颜色": sku.color, "尺码": sku.size,
            "数量": quantity, "成本": pd.NA, "备注": reason,
        }]),
        created_by="Andy", source_type=source,
        batch_id=str(uuid5(NAMESPACE_URL, seed)),
    )


def _current(sku):
    row = (
        supabase.table("inventory_items").select("quantity")
        .eq("department", sku.department).eq("category", sku.category)
        .eq("brand", sku.brand).eq("material", sku.material)
        .eq("color", sku.color).eq("size", sku.size)
        .single().execute().data
    )
    return int(row["quantity"])


def _movement_count(sku):
    return len(
        supabase.table("inventory_movements").select("id")
        .eq("department", sku.department).eq("category", sku.category)
        .eq("brand", sku.brand).eq("material", sku.material)
        .eq("color", sku.color).eq("size", sku.size)
        .limit(1).execute().data or []
    )


if __name__ == "__main__":
    print(reconcile())
