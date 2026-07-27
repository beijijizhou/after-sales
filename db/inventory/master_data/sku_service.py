from uuid import uuid4

import pandas as pd

from db.inventory.master_data.repository import load_sku_catalog


IDENTITY_COLUMNS = ["category", "brand", "material", "color", "size"]


def create_skus(
    supabase, department, category, rows, brands, created_by
):
    existing = load_sku_catalog(supabase, department["code"])
    existing_keys = {
        _sku_key(row) for row in existing.to_dict("records")
    }
    brand_ids = dict(zip(brands.get("name", []), brands.get("id", [])))
    payload = []
    skipped = 0
    for source in pd.DataFrame(rows).to_dict("records"):
        if not any(
            _clean(source.get(column))
            for column in ["SKU 名称", "品牌", "材质", "颜色", "规格"]
        ):
            continue
        brand = _clean(source.get("品牌"))
        material = _clean(source.get("材质"))
        color = _clean(source.get("颜色"))
        specification = _specification(source, category)
        key = _normalized_key((
            category["name"], brand, material, color, specification
        ))
        if key in existing_keys:
            skipped += 1
            continue
        item_id = uuid4()
        sku_name = _clean(source.get("SKU 名称")) or _build_sku_name(
            category["name"], brand, material, color, specification
        )
        payload.append({
            "id": str(item_id),
            "sku_code": f"SKU-{item_id.hex[:10].upper()}",
            "sku_name": sku_name,
            "department": department["code"],
            "department_id": department["id"],
            "category": category["name"],
            "category_id": category["id"],
            "brand": brand,
            "brand_id": brand_ids.get(brand),
            "material": material,
            "color": color,
            "size": specification,
            "model": (
                specification
                if category["specification_type"] == "model"
                else None
            ),
            "unit": _clean(source.get("单位")) or "件",
            "quantity": 0,
            "unit_cost": 0,
            "品牌": brand,
            "材质": material,
            "成本": 0,
            "created_by": created_by,
        })
        existing_keys.add(key)
    if payload:
        supabase.table("inventory_items").insert(payload).execute()
    return len(payload), skipped


def update_skus(supabase, original_df, edited_df, categories, brands):
    category_map = {
        row["name"]: row for row in categories.to_dict("records")
    }
    brand_map = dict(zip(brands.get("name", []), brands.get("id", [])))
    originals = original_df.set_index("id")
    prepared = _validate_updates(edited_df, category_map)
    updated = 0
    for row, category, specification in prepared:
        original = originals.loc[row["id"]]
        if not _has_changes(row, original):
            continue
        brand = _clean(row.get("brand"))
        values = {
            "sku_name": _required(row.get("sku_name"), "SKU 名称"),
            "category": category["name"],
            "category_id": category["id"],
            "brand": brand,
            "brand_id": brand_map.get(brand),
            "material": _clean(row.get("material")),
            "color": _clean(row.get("color")),
            "size": specification,
            "model": (
                specification
                if category["specification_type"] == "model"
                else None
            ),
            "unit": _clean(row.get("unit")) or "件",
            "is_active": bool(row.get("is_active")),
            "品牌": brand,
            "材质": _clean(row.get("material")),
        }
        supabase.table("inventory_items").update(values).eq(
            "id", row["id"]
        ).execute()
        updated += 1
    return updated


def _validate_updates(edited_df, category_map):
    seen_keys = set()
    prepared = []
    for row in edited_df.to_dict("records"):
        if row.get("category") not in category_map:
            raise ValueError("请选择有效品类")
        category = category_map[row["category"]]
        specification = _specification(row, category)
        key = _normalized_key((
            category["name"], row.get("brand"), row.get("material"),
            row.get("color"), specification,
        ))
        if key in seen_keys:
            raise ValueError("修改后存在重复 SKU，请检查品类、品牌、材质、颜色和规格")
        seen_keys.add(key)
        prepared.append((row, category, specification))
    return prepared


def _specification(row, category):
    if category["specification_type"] == "none":
        return ""
    value = _clean(row.get("规格")).upper()
    if not value:
        name = _clean(row.get("sku_name") or row.get("SKU 名称")) or "SKU"
        raise ValueError(f"{name} 缺少尺码 / 型号")
    return value


def _has_changes(row, original):
    return any(
        _clean(row.get(column)) != _clean(original.get(column))
        for column in [
            "sku_name", "category", "brand", "material",
            "color", "规格", "unit", "is_active",
        ]
    )


def _sku_key(row):
    return _normalized_key(
        tuple(_clean(row.get(column)) for column in IDENTITY_COLUMNS)
    )


def _build_sku_name(category, brand, material, color, specification):
    parts = []
    seen = set()
    for value in [category, brand, material, color, specification]:
        cleaned = _clean(value)
        normalized = cleaned.casefold()
        if cleaned and normalized not in seen:
            parts.append(cleaned)
            seen.add(normalized)
    return " ".join(parts)


def _normalized_key(values):
    return tuple(_clean(value).casefold() for value in values)


def _required(value, label):
    result = _clean(value)
    if not result:
        raise ValueError(f"{label}不能为空")
    return result


def _clean(value):
    return "" if pd.isna(value) else str(value).strip()
