from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from db.inventory.operations.adjustments import apply_adjustment_rows


IDENTITY_COLUMNS = ["category", "brand", "material", "color", "size"]


def load_uninitialized_skus(supabase, department, category=""):
    catalog = pd.DataFrame(
        supabase.table("inventory_items")
        .select(
            "id,sku_code,sku_name,department,category,brand,material,"
            "color,size,model,unit,quantity,is_active"
        )
        .eq("department", department)
        .limit(10000)
        .execute()
        .data
    )
    movements = pd.DataFrame(
        supabase.table("inventory_movements")
        .select("category,brand,material,color,size,quantity_change")
        .eq("department", department)
        .gt("quantity_change", 0)
        .limit(10000)
        .execute()
        .data
    )
    return find_uninitialized_skus(catalog, movements, category)


def find_uninitialized_skus(catalog, movements, category=""):
    if catalog.empty:
        return catalog
    catalog = catalog.copy()
    if category:
        catalog = catalog[catalog["category"] == category]
    catalog = catalog[
        catalog["is_active"].fillna(True)
        & (pd.to_numeric(catalog["quantity"], errors="coerce").fillna(0) == 0)
    ].copy()
    if catalog.empty or movements.empty:
        return catalog.reset_index(drop=True)
    initialized = {
        _identity(row)
        for row in movements.to_dict("records")
    }
    pending = catalog[
        ~catalog.apply(
            lambda row: _identity(row.to_dict()) in initialized,
            axis=1,
        )
    ]
    return pending.reset_index(drop=True)


def initialize_sku_inventory(
    supabase, department, rows, created_by="system"
):
    source = pd.DataFrame(rows).copy()
    source["初始库存"] = pd.to_numeric(
        source["初始库存"], errors="coerce"
    ).fillna(0).astype(int)
    source = source[source["初始库存"] > 0]
    if source.empty:
        return 0

    movement_date = datetime.now(
        ZoneInfo("America/New_York")
    ).date()
    saved = 0
    for category, category_rows in source.groupby("category"):
        adjustment_rows = pd.DataFrame({
            "日期": movement_date,
            "操作": "增加",
            "品牌": category_rows["brand"].fillna(""),
            "材质": category_rows["material"].fillna(""),
            "颜色": category_rows["color"].fillna(""),
            "尺码": category_rows["size"].fillna(""),
            "数量": category_rows["初始库存"],
            "成本": pd.NA,
            "备注": "初始化库存",
        })
        apply_adjustment_rows(
            supabase,
            department,
            category,
            adjustment_rows,
            created_by=created_by,
            source_type="opening",
        )
        saved += len(category_rows)
    return saved


def _identity(row):
    return tuple(
        str(row.get(column) or "").strip().casefold()
        for column in IDENTITY_COLUMNS
    )
