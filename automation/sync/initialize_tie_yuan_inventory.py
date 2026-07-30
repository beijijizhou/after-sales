from datetime import date
from uuid import NAMESPACE_URL, uuid5

import pandas as pd

from db.inventory.operations.adjustments import apply_adjustment_rows
from db.supabase_client import supabase


SKU = {
    "品牌": "",
    "材质": "铁牌",
    "颜色": "白",
    "尺码": "YUAN",
}
OPENING_DATE = date(2026, 5, 1)
OPENING_QUANTITY = 50_000
DAILY_USAGE = {
    "2026-07-05": 360,
    "2026-07-06": 431,
    "2026-07-07": 315,
    "2026-07-08": 310,
    "2026-07-10": 661,
    "2026-07-12": 238,
    "2026-07-13": 329,
    "2026-07-14": 224,
    "2026-07-15": 298,
    "2026-07-20": 460,
    "2026-07-21": 592,
    "2026-07-22": 298,
    "2026-07-23": 336,
    "2026-07-24": 359,
    "2026-07-25": 469,
    "2026-07-26": 430,
    "2026-07-27": 451,
    "2026-07-28": 352,
    "2026-07-29": 272,
    "2026-07-30": 380,
}


def initialize_tie_yuan_inventory():
    if _movement_total() != 0 or _current_quantity() != 0:
        raise ValueError("圆铁 YUAN 已有库存或流水，停止重复初始化")

    _apply(
        OPENING_DATE,
        "增加",
        OPENING_QUANTITY,
        "圆铁 YUAN 期初库存｜用户确认 50000片｜2026-05-01",
        "opening",
        "uv-tie-yuan-opening-2026-05-01",
    )
    for movement_date, quantity in DAILY_USAGE.items():
        _apply(
            date.fromisoformat(movement_date),
            "扣减",
            quantity,
            f"Google Sheets UV每日消耗｜{movement_date}｜Tie_yuan_2020",
            "bulk",
            f"uv-google-sheets-tie-yuan-{movement_date}",
        )

    expected = OPENING_QUANTITY - sum(DAILY_USAGE.values())
    actual = _current_quantity()
    if actual != expected:
        raise ValueError(f"保存后库存核验失败：{actual} / {expected}")
    return {
        "opening": OPENING_QUANTITY,
        "usage": sum(DAILY_USAGE.values()),
        "remaining": actual,
        "days": len(DAILY_USAGE),
    }


def _apply(
    movement_date, operation, quantity, reason, source_type, batch_seed
):
    row = pd.DataFrame([{
        "日期": movement_date,
        "操作": operation,
        **SKU,
        "数量": quantity,
        "成本": pd.NA,
        "备注": reason,
    }])
    apply_adjustment_rows(
        supabase,
        "UV",
        "铁板画",
        row,
        created_by="Andy",
        source_type=source_type,
        batch_id=str(uuid5(NAMESPACE_URL, batch_seed)),
    )


def _current_quantity():
    rows = (
        supabase.table("inventory_items")
        .select("quantity")
        .eq("department", "UV")
        .eq("category", "铁板画")
        .eq("brand", "")
        .eq("material", "铁牌")
        .eq("color", "白")
        .eq("size", "YUAN")
        .execute()
        .data
        or []
    )
    if len(rows) != 1:
        raise ValueError(f"圆铁 YUAN SKU 数量异常：{len(rows)}")
    return int(rows[0]["quantity"])


def _movement_total():
    rows = (
        supabase.table("inventory_movements")
        .select("quantity_change")
        .eq("department", "UV")
        .eq("category", "铁板画")
        .eq("brand", "")
        .eq("material", "铁牌")
        .eq("color", "白")
        .eq("size", "YUAN")
        .limit(5000)
        .execute()
        .data
        or []
    )
    return sum(int(row["quantity_change"]) for row in rows)


if __name__ == "__main__":
    print(initialize_tie_yuan_inventory())
