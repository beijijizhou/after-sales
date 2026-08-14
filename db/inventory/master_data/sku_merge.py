"""Persistent SKU merge rules and manager-facing preview models."""

import pandas as pd

from db.inventory.core.constants import SIZE_COLUMNS
from utils.sku_sorting import sort_sku_rows


GROUP_COLUMNS = ["category", "brand", "material", "color"]


def build_sku_merge_groups(catalog):
    source = pd.DataFrame(catalog).copy()
    if source.empty:
        return pd.DataFrame(columns=[*GROUP_COLUMNS, "SKU数", "当前库存"])
    source["quantity"] = pd.to_numeric(
        source.get("quantity"), errors="coerce"
    ).fillna(0).astype(int)
    return (
        source.groupby(GROUP_COLUMNS, dropna=False, as_index=False)
        .agg(SKU数=("id", "count"), 当前库存=("quantity", "sum"))
    )


def group_key(row):
    return tuple(str(row.get(column) or "").strip() for column in GROUP_COLUMNS)


def group_label(key):
    category, brand, material, color = key
    return "｜".join(value or "未填写" for value in [category, material, color, brand])


def compatible_merge_targets(groups, source_key, available_brands=None):
    source_category, source_brand, source_material, source_color = source_key
    result = []
    for row in pd.DataFrame(groups).to_dict("records"):
        key = group_key(row)
        if (
            key[0] == source_category
            and key[2] == source_material
            and key[3] == source_color
            and key[1] != source_brand
        ):
            result.append(key)
    existing = set(result)
    for brand in available_brands or []:
        target = (
            source_category, str(brand or "").strip(),
            source_material, source_color,
        )
        if target[1] and target[1] != source_brand and target not in existing:
            result.append(target)
            existing.add(target)
    return result


def build_sku_group_merge_preview(catalog, source_key, target_key):
    source = pd.DataFrame(catalog).copy()
    if source.empty:
        return pd.DataFrame()
    source_rows = _matching_group(source, source_key)
    target_rows = _matching_group(source, target_key)
    rows = []
    sizes = list(dict.fromkeys([
        *SIZE_COLUMNS,
        *source_rows.get("size", pd.Series(dtype=str)).astype(str).tolist(),
        *target_rows.get("size", pd.Series(dtype=str)).astype(str).tolist(),
    ]))
    for size in sizes:
        source_quantity = _size_quantity(source_rows, size)
        target_quantity = _size_quantity(target_rows, size)
        if not source_quantity and not target_quantity:
            continue
        rows.append({
            "材质": source_key[2], "颜色": source_key[3], "尺码": size,
            "来源品牌": source_key[1], "来源当前库存": source_quantity,
            "目标品牌": target_key[1], "目标当前库存": target_quantity,
            "并入后库存": source_quantity + target_quantity,
        })
    return sort_sku_rows(
        pd.DataFrame(rows), material="材质", color="颜色", size="尺码"
    )


def load_sku_merge_rules(supabase, department=None):
    query = supabase.table("inventory_sku_merge_rules").select(
        "id,department,category,source_brand,target_brand,material,color,"
        "status,created_by,created_at,deactivated_by,deactivated_at"
    )
    if department:
        query = query.eq("department", department)
    return pd.DataFrame(query.order("created_at", desc=True).execute().data or [])


def merge_sku_groups(
    supabase, department, source_key, target_key, business_date, operated_by,
):
    result = supabase.rpc("merge_inventory_sku_group", {
        "p_department": department,
        "p_category": source_key[0],
        "p_source_brand": source_key[1],
        "p_target_brand": target_key[1],
        "p_material": source_key[2],
        "p_color": source_key[3],
        "p_business_date": business_date.isoformat(),
        "p_operated_by": operated_by,
    }).execute().data
    try:
        supabase.rpc("create_inventory_snapshot", {
            "p_department": department,
            "p_category": source_key[0],
            "p_snapshot_date": business_date.isoformat(),
        }).execute()
    except Exception:
        pass
    return result


def _matching_group(source, key):
    mask = pd.Series(True, index=source.index)
    for column, value in zip(GROUP_COLUMNS, key):
        mask &= source[column].fillna("").astype(str).str.strip().eq(value)
    return source[mask]


def _size_quantity(source, size):
    rows = source[source.get("size", "").astype(str).eq(size)]
    return int(pd.to_numeric(rows.get("quantity"), errors="coerce").fillna(0).sum())
