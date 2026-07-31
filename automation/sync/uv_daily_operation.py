from dataclasses import asdict

import pandas as pd

from automation.sync.uv_sheet_inventory import (
    InventorySku,
    existing_usage,
    sync_usage_to_inventory,
)


UV_PRODUCT_SKUS = {
    "600ml ZhiBei": InventorySku(
        "UV", "保温杯", "", "直杯", "", "600ML"
    ),
    "Caffee": InventorySku(
        "UV", "保温杯", "", "咖啡杯", "", "600ML"
    ),
    "CHEPAI": InventorySku(
        "UV", "铁板画", "", "铁牌", "白", "1530"
    ),
    "Guazhong_2525": InventorySku(
        "UV", "木板画", "", "挂钟", "白", "25"
    ),
    "Lv_2030": InventorySku(
        "UV", "铁板画", "", "铝牌", "白", "2030"
    ),
    "Lv_yuan_2020": InventorySku(
        "UV", "铁板画", "", "铝牌", "白", "YUAN"
    ),
    "Muban_2030": InventorySku(
        "UV", "木板画", "", "木板", "白", "2030"
    ),
    "Tie_1040": InventorySku(
        "UV", "铁板画", "", "铁牌", "白", "1040"
    ),
    "Tie_2030": InventorySku(
        "UV", "铁板画", "", "铁牌", "白", "2030"
    ),
    "Tie_3040": InventorySku(
        "UV", "铁板画", "", "铁牌", "白", "3040"
    ),
    "Tie_yuan_2020": InventorySku(
        "UV", "铁板画", "", "铁牌", "白", "YUAN"
    ),
}

SYNCABLE_STATUSES = {
    "可扣减",
    "已同步",
    "待分配 SKU（本次不扣）",
}


def build_daily_sync_preview(
    supabase, summary, movement_date, inventory_df
):
    rows = []
    inventory = inventory_df.copy()
    for product, quantity in summary.items():
        sku = UV_PRODUCT_SKUS.get(product)
        if sku is None:
            rows.append({
                "表格产品": product, "品类": "", "材质": "",
                "颜色": "", "型号": "", "当日消耗": quantity,
                "当前库存": 0, "预计扣减": 0, "扣减后库存": 0,
                "状态": "待分配 SKU（本次不扣）",
            })
            continue
        current = _current_quantity(inventory, sku)
        saved = existing_usage(supabase, sku, movement_date)
        planned = quantity if saved == 0 else 0
        if saved and saved != quantity:
            status = f"已扣 {saved}，表格为 {quantity}"
        elif saved:
            status = "已同步"
        elif current < quantity:
            status = "库存不足"
        else:
            status = "可扣减"
        rows.append({
            "表格产品": product,
            "品类": sku.category,
            "材质": sku.material,
            "颜色": sku.color,
            "型号": sku.size,
            "当日消耗": quantity,
            "当前库存": current,
            "预计扣减": planned,
            "扣减后库存": current - planned,
            "状态": status,
        })
    return pd.DataFrame(rows)


def apply_daily_sync(supabase, preview, movement_date, created_by):
    blocking = preview[
        ~preview["状态"].isin(SYNCABLE_STATUSES)
    ]
    if not blocking.empty:
        raise ValueError("存在历史扣减数量与表格不一致的 SKU")
    imported = skipped = 0
    for row in preview.to_dict("records"):
        if row["状态"] == "待分配 SKU（本次不扣）":
            continue
        sku = UV_PRODUCT_SKUS[row["表格产品"]]
        saved, existing = sync_usage_to_inventory(
            supabase,
            sku,
            {movement_date: int(row["当日消耗"])},
            created_by,
            row["表格产品"],
        )
        imported += sum(saved.values())
        skipped += sum(existing.values())
    return imported, skipped


def _current_quantity(inventory, sku):
    identity = asdict(sku)
    rows = inventory
    for column in ["department", "category", "brand", "material", "color", "size"]:
        if column not in rows.columns:
            return 0
        rows = rows[
            rows[column].fillna("").astype(str) == identity[column]
        ]
    return int(pd.to_numeric(
        rows["quantity"], errors="coerce"
    ).fillna(0).sum())
