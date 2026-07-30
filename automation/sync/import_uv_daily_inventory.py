from datetime import datetime
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

import pandas as pd

from db.inventory.container.workflow import (
    confirm_container_arrival,
    post_container_inventory,
)
from db.inventory.operations.adjustments import apply_adjustment_rows
from db.supabase_client import supabase


NY_TIMEZONE = ZoneInfo("America/New_York")
CONTAINER_KEY = "9柜"
OPERATOR = "Andy"

DAILY_USAGE = {
    "2026-07-23": {
        ("铁牌", "1530"): 69,
        ("铝牌", "2030"): 204 + 2488,
        ("铝牌", "YUAN"): 243,
        ("铁牌", "1040"): 553,
        ("铁牌", "3040"): 205,
    },
    "2026-07-24": {
        ("铁牌", "1530"): 75,
        ("铝牌", "2030"): 79 + 2389,
        ("铝牌", "YUAN"): 294,
        ("铁牌", "1040"): 334,
        ("铁牌", "3040"): 297,
    },
    "2026-07-25": {
        ("铁牌", "1530"): 14,
        ("铝牌", "2030"): 86 + 1733,
        ("铝牌", "YUAN"): 273,
        ("铁牌", "1040"): 173,
        ("铁牌", "3040"): 251,
    },
    "2026-07-26": {
        ("铁牌", "1530"): 47,
        ("铝牌", "2030"): 42 + 2052,
        ("铝牌", "YUAN"): 263,
        ("铁牌", "1040"): 454,
        ("铁牌", "3040"): 153,
    },
    "2026-07-27": {
        ("铁牌", "1530"): 162,
        ("铝牌", "2030"): 219 + 2538,
        ("铝牌", "YUAN"): 317,
        ("铁牌", "1040"): 644,
        ("铁牌", "3040"): 342,
    },
    "2026-07-28": {
        ("铁牌", "1530"): 118,
        ("铝牌", "2030"): 234 + 2144,
        ("铝牌", "YUAN"): 293,
        ("铁牌", "1040"): 435,
        ("铁牌", "3040"): 169,
    },
    "2026-07-29": {
        ("铁牌", "1530"): 59,
        ("铝牌", "2030"): 136,
        ("铝牌", "YUAN"): 271,
        ("铁牌", "1040"): 424,
        ("铁牌", "2030"): 1996,
        ("铁牌", "3040"): 272,
    },
}


def import_uv_daily_inventory():
    _post_ninth_container()
    _validate_inventory()
    imported = []
    skipped = []
    for movement_date, usage in DAILY_USAGE.items():
        reason = _reason(movement_date)
        expected_total = sum(usage.values())
        existing_total = _existing_total(movement_date, reason)
        if existing_total:
            if existing_total != expected_total:
                raise ValueError(
                    f"{movement_date} 已有 {existing_total} 件，"
                    f"但本次应为 {expected_total} 件"
                )
            skipped.append((movement_date, existing_total))
            continue
        rows = _build_rows(movement_date, usage, reason)
        apply_adjustment_rows(
            supabase,
            "UV",
            "铁板画",
            rows,
            created_by=OPERATOR,
            source_type="bulk",
            batch_id=str(uuid5(
                NAMESPACE_URL, f"uv-google-sheets-{movement_date}"
            )),
        )
        saved_total = _existing_total(movement_date, reason)
        if saved_total != expected_total:
            raise ValueError(
                f"{movement_date} 保存后核验失败："
                f"{saved_total} / {expected_total}"
            )
        imported.append((movement_date, saved_total))
    return imported, skipped


def _post_ninth_container():
    rows = (
        supabase.table("inventory_container_imports")
        .select("status")
        .eq("container_key", CONTAINER_KEY)
        .execute()
        .data
    )
    states = {row.get("status") for row in rows}
    if not states:
        raise ValueError("数据库中没有找到9柜")
    if states == {"在途"}:
        confirm_container_arrival(
            supabase,
            CONTAINER_KEY,
            datetime.now(NY_TIMEZONE),
            OPERATOR,
            "用户确认9柜已到，UV每日消耗导入前完成到柜登记",
        )
        states = {"已到柜"}
    if states in ({"已到柜"}, {"已到货"}):
        post_container_inventory(
            supabase,
            CONTAINER_KEY,
            OPERATOR,
            "UV每日消耗导入前确认入库",
        )
        return
    if states != {"已入库"}:
        raise ValueError(f"9柜状态异常：{states}")


def _validate_inventory():
    required = {}
    for usage in DAILY_USAGE.values():
        for key, quantity in usage.items():
            required[key] = required.get(key, 0) + quantity
    rows = (
        supabase.table("inventory_items")
        .select("material,size,quantity")
        .eq("department", "UV")
        .eq("category", "铁板画")
        .eq("brand", "")
        .eq("color", "白")
        .execute()
        .data
    )
    available = {
        (row["material"], row["size"]): int(row["quantity"])
        for row in rows
    }
    shortages = [
        f"{material}/{size}: {available.get((material, size), 0)}"
        f" < {quantity}"
        for (material, size), quantity in required.items()
        if available.get((material, size), 0) < quantity
    ]
    if shortages:
        raise ValueError("库存不足：" + "；".join(shortages))


def _build_rows(movement_date, usage, reason):
    return pd.DataFrame([
        {
            "日期": pd.Timestamp(movement_date).date(),
            "操作": "扣减",
            "品牌": "",
            "材质": material,
            "颜色": "白",
            "尺码": size,
            "数量": quantity,
            "备注": reason,
        }
        for (material, size), quantity in usage.items()
    ])


def _existing_total(movement_date, reason):
    rows = (
        supabase.table("inventory_movements")
        .select("quantity_change")
        .eq("department", "UV")
        .eq("category", "铁板画")
        .eq("movement_date", movement_date)
        .eq("reason", reason)
        .execute()
        .data
    )
    return sum(abs(int(row["quantity_change"])) for row in rows)


def _reason(movement_date):
    tie_rule = (
        "Tie_2030自7月29日起按铁牌扣减"
        if movement_date >= "2026-07-29"
        else "7月29日前Tie_2030按铝牌扣减"
    )
    return (
        f"Google Sheets UV每日消耗｜{movement_date}｜"
        f"{tie_rule}"
    )


if __name__ == "__main__":
    imported_rows, skipped_rows = import_uv_daily_inventory()
    print("已导入：", imported_rows)
    print("已跳过：", skipped_rows)
