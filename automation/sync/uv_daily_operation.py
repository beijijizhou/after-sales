from dataclasses import asdict
from uuid import NAMESPACE_URL, uuid5

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
PHONE_CASE_PRODUCT = "Iphone"
PHONE_CASE_CATEGORY = "手机壳"
PHONE_CASE_PENDING_STATUS = "待分配手机壳型号"

SYNCABLE_STATUSES = {
    "可扣减",
    "已同步",
    "待分配 SKU（本次不扣）",
    PHONE_CASE_PENDING_STATUS,
}


def build_daily_sync_preview(
    supabase, summary, movement_date, inventory_df
):
    rows = []
    inventory = inventory_df.copy()
    for product, quantity in summary.items():
        if product == PHONE_CASE_PRODUCT:
            phone_inventory = _phone_case_inventory(inventory)
            current = int(pd.to_numeric(
                phone_inventory.get("quantity", pd.Series(dtype=float)),
                errors="coerce",
            ).fillna(0).sum())
            saved = existing_phone_case_usage(supabase, movement_date)
            if saved and saved != quantity:
                status = f"已扣 {saved}，表格为 {quantity}"
            elif saved:
                status = "已同步"
            else:
                status = PHONE_CASE_PENDING_STATUS
            rows.append({
                "表格产品": product,
                "品类": PHONE_CASE_CATEGORY,
                "材质": "按型号分配",
                "颜色": "",
                "型号": "",
                "当日消耗": quantity,
                "当前库存": current,
                "预计扣减": 0,
                "扣减后库存": current,
                "状态": status,
            })
            continue
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
    batch_id = str(uuid5(
        NAMESPACE_URL,
        f"UV-Google-Sheets-daily-consumption-{movement_date.isoformat()}",
    ))
    for row in preview.to_dict("records"):
        if row["状态"] in {
            "待分配 SKU（本次不扣）", PHONE_CASE_PENDING_STATUS,
        }:
            continue
        if row["表格产品"] == PHONE_CASE_PRODUCT:
            sku = InventorySku(
                "UV", PHONE_CASE_CATEGORY,
                str(row.get("品牌") or ""),
                str(row.get("材质") or ""),
                str(row.get("颜色") or ""),
                str(row.get("型号") or ""),
            )
        else:
            sku = UV_PRODUCT_SKUS[row["表格产品"]]
        saved, existing = sync_usage_to_inventory(
            supabase,
            sku,
            {movement_date: int(row["当日消耗"])},
            created_by,
            row["表格产品"],
            batch_id=batch_id,
        )
        imported += sum(saved.values())
        skipped += sum(existing.values())
    return imported, skipped


def build_daily_deduction_scope(
    preview, phone_case_allocations=None, phone_case_complete=False,
):
    """Keep unresolved phone cases outside the production deduction gate."""
    source = pd.DataFrame(preview).copy()
    production = source[
        source["表格产品"] != PHONE_CASE_PRODUCT
    ].copy()
    phone_rows = pd.DataFrame(phone_case_allocations).copy()
    if not phone_case_complete:
        phone_rows = phone_rows.iloc[0:0].copy()
    ready = pd.concat([production, phone_rows], ignore_index=True)
    pending = ready[ready["状态"] == "可扣减"].copy()
    blocking = production[
        ~production["状态"].isin(SYNCABLE_STATUSES)
    ].copy()
    return ready, pending, blocking


def build_phone_case_allocation_preview(inventory_df, allocations):
    inventory = _phone_case_inventory(inventory_df)
    columns = [
        "表格产品", "品类", "品牌", "材质", "颜色", "型号",
        "当日消耗", "当前库存", "预计扣减", "扣减后库存", "状态",
    ]
    if inventory.empty or not allocations:
        return pd.DataFrame(columns=columns)
    lookup = {
        phone_case_sku_key(row): row
        for row in inventory.to_dict("records")
    }
    rows = []
    for key, raw_quantity in allocations.items():
        source = lookup.get(str(key))
        parsed_quantity = pd.to_numeric(raw_quantity, errors="coerce")
        quantity = 0 if pd.isna(parsed_quantity) else max(int(parsed_quantity), 0)
        if source is None or quantity <= 0:
            continue
        parsed_current = pd.to_numeric(
            source.get("quantity"), errors="coerce"
        )
        current = 0 if pd.isna(parsed_current) else int(parsed_current)
        rows.append({
            "表格产品": PHONE_CASE_PRODUCT,
            "品类": PHONE_CASE_CATEGORY,
            "品牌": str(source.get("brand") or ""),
            "材质": str(source.get("material") or ""),
            "颜色": str(source.get("color") or ""),
            "型号": str(source.get("size") or source.get("model") or ""),
            "当日消耗": quantity,
            "当前库存": current,
            "预计扣减": quantity,
            "扣减后库存": current - quantity,
            "状态": "可扣减" if current >= quantity else "库存不足",
        })
    return pd.DataFrame(rows, columns=columns)


def phone_case_sku_key(row):
    return "|".join(str(row.get(column) or "").strip() for column in (
        "brand", "material", "color", "size",
    ))


def phone_case_sku_label(row):
    parts = [
        str(row.get("material") or "").strip(),
        str(row.get("size") or row.get("model") or "").strip(),
    ]
    return "｜".join(part for part in parts if part)


def existing_phone_case_usage(supabase, movement_date):
    rows = (
        supabase.table("inventory_movements")
        .select("quantity_change")
        .eq("department", "UV")
        .eq("category", PHONE_CASE_CATEGORY)
        .eq("movement_date", movement_date.isoformat())
        .like("reason", f"Google Sheets UV每日消耗｜{movement_date.isoformat()}%")
        .execute().data or []
    )
    return sum(
        abs(int(row.get("quantity_change") or 0)) for row in rows
        if int(row.get("quantity_change") or 0) < 0
    )


def _phone_case_inventory(inventory_df):
    inventory = pd.DataFrame(inventory_df).copy()
    if inventory.empty or "category" not in inventory:
        return inventory.iloc[0:0]
    inventory = inventory[
        inventory["category"].fillna("").astype(str).eq(PHONE_CASE_CATEGORY)
    ].copy()
    if "is_active" in inventory:
        inventory = inventory[inventory["is_active"].fillna(True)]
    if "material" in inventory:
        inventory = inventory[
            inventory["material"].fillna("").astype(str).str.strip().ne("")
        ]
    return inventory.reset_index(drop=True)


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
