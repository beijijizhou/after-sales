from uuid import uuid4

import pandas as pd

from db.inventory.master_data.repository import load_sku_catalog


IDENTITY_COLUMNS = ["category", "brand", "material", "color", "size"]


def create_skus(
    supabase, department, category, rows, brands, created_by, materials=None
):
    existing = load_sku_catalog(supabase, department["code"])
    existing_keys = {
        _sku_key(row) for row in existing.to_dict("records")
    }
    brand_ids = dict(zip(brands.get("name", []), brands.get("id", [])))
    material_names = _option_names(materials)
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
        if material_names is not None and material.casefold() not in material_names:
            raise ValueError("请选择有效材质")
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


def update_skus(
    supabase, original_df, edited_df, categories, brands, materials=None,
    department_code=None, changed_by="system",
):
    edited_df = propagate_sku_identity_changes(original_df, edited_df)
    category_map = {
        row["name"]: row for row in categories.to_dict("records")
    }
    brand_map = dict(zip(brands.get("name", []), brands.get("id", [])))
    originals = original_df.set_index("id")
    _validate_updates(
        edited_df, category_map, _option_names(materials),
        allow_duplicates=True,
    )
    identity_changes, identity_change_ids = build_sku_identity_changes(
        original_df, edited_df
    )
    remaining_edited = edited_df[
        ~edited_df["id"].isin(identity_change_ids)
    ]
    prepared = _validate_updates(
        remaining_edited, category_map, _option_names(materials)
    )
    updated = 0
    if identity_changes:
        original_source = pd.DataFrame(original_df)
        inferred_department = (
            _clean(original_source["department"].iloc[0])
            if not original_source.empty and "department" in original_source
            else "DTF"
        )
        department_code = _clean(department_code) or inferred_department
        supabase.rpc("update_inventory_sku_identities", {
            "p_department": department_code,
            "p_changes": identity_changes,
            "p_changed_by": _clean(changed_by) or "system",
        }).execute()
        _refresh_changed_group_metadata(
            supabase, department_code, identity_changes,
            category_map, brand_map,
        )
        updated += len(identity_change_ids)
    for row, category, specification in prepared:
        original = originals.loc[row["id"]]
        if not _has_changes(row, original):
            continue
        brand = _clean(row.get("brand"))
        material = _clean(row.get("material"))
        color = _clean(row.get("color"))
        values = {
            "sku_name": _build_sku_name(
                category["name"], brand, material, color, specification
            ),
            "category": category["name"],
            "category_id": category["id"],
            "brand": brand,
            "brand_id": brand_map.get(brand),
            "material": material,
            "color": color,
            "size": specification,
            "model": (
                specification
                if category["specification_type"] == "model"
                else None
            ),
            "unit": _clean(row.get("unit")) or "件",
            "is_active": bool(row.get("is_active")),
            "品牌": brand,
            "材质": material,
        }
        supabase.table("inventory_items").update(values).eq(
            "id", row["id"]
        ).execute()
        updated += 1
    return updated


def propagate_sku_identity_changes(original_df, edited_df):
    group_columns = ["category", "brand", "material", "color"]
    originals = pd.DataFrame(original_df).copy()
    result = pd.DataFrame(edited_df).copy().set_index("id")
    for old_values, group in originals.groupby(
        group_columns, dropna=False, sort=False
    ):
        old_group = tuple(_clean(value) for value in old_values)
        group_ids = group["id"].tolist()
        changed_groups = {
            tuple(_clean(row.get(column)) for column in group_columns)
            for row in result.loc[group_ids].to_dict("records")
            if _normalized_key(tuple(
                _clean(row.get(column)) for column in group_columns
            )) != _normalized_key(old_group)
        }
        if len(changed_groups) != 1:
            continue
        new_group = next(iter(changed_groups))
        for column, value in zip(group_columns, new_group):
            result.loc[group_ids, column] = value
    return result.reset_index()


def build_sku_identity_changes(original_df, edited_df):
    group_columns = ["category", "brand", "material", "color"]
    originals = pd.DataFrame(original_df).copy()
    edited = pd.DataFrame(edited_df).set_index("id")
    changes = []
    changed_ids = set()
    for old_values, group in originals.groupby(
        group_columns, dropna=False, sort=False
    ):
        group_ids = group["id"].tolist()
        final_rows = edited.loc[group_ids]
        final_groups = {
            tuple(_clean(row.get(column)) for column in group_columns)
            for row in final_rows.to_dict("records")
        }
        old_group = tuple(_clean(value) for value in old_values)
        if len(final_groups) != 1:
            continue
        new_group = next(iter(final_groups))
        if _normalized_key(old_group) == _normalized_key(new_group):
            continue
        changes.append({
            **{
                f"old_{column}": value
                for column, value in zip(group_columns, old_group)
            },
            **{
                f"new_{column}": value
                for column, value in zip(group_columns, new_group)
            },
        })
        changed_ids.update(group_ids)
    return changes, changed_ids


def build_sku_merge_preview(original_df, edited_df):
    group_columns = ["category", "brand", "material", "color"]
    source = pd.DataFrame(original_df).copy()
    normalized_edited = propagate_sku_identity_changes(
        original_df, edited_df
    )
    changes, _ = build_sku_identity_changes(source, normalized_edited)
    previews = []
    for change in changes:
        old_values = tuple(change[f"old_{column}"] for column in group_columns)
        new_values = tuple(change[f"new_{column}"] for column in group_columns)
        old_rows = _rows_matching_group(source, group_columns, old_values)
        target_rows = _rows_matching_group(source, group_columns, new_values)
        if target_rows.empty:
            continue
        old_sizes = set(
            old_rows.get("规格", old_rows.get("size", [])).astype(str)
        )
        target_sizes = set(
            target_rows.get("规格", target_rows.get("size", [])).astype(str)
        )
        quantities = pd.Series(old_rows.get("quantity", 0), index=old_rows.index)
        previews.append({
            "old_brand": change["old_brand"] or "未填写品牌",
            "new_brand": change["new_brand"] or "未填写品牌",
            "sku_count": len(old_rows),
            "overlap_count": len(old_sizes & target_sizes),
            "quantity": int(pd.to_numeric(
                quantities, errors="coerce"
            ).fillna(0).sum()),
        })
    return previews


def _rows_matching_group(source, columns, values):
    mask = pd.Series(True, index=source.index)
    for column, value in zip(columns, values):
        actual = source[column].fillna("").astype(str).str.strip().str.casefold()
        mask &= actual.eq(_clean(value).casefold())
    return source[mask]


def _refresh_changed_group_metadata(
    supabase, department_code, changes, category_map, brand_map,
):
    for change in changes:
        category_name = change["new_category"]
        brand = change["new_brand"]
        material = change["new_material"]
        color = change["new_color"]
        category = category_map[category_name]
        query = (
            supabase.table("inventory_items")
            .select("id,size")
            .eq("department", department_code)
            .eq("category", category_name)
            .eq("brand", brand)
            .eq("material", material)
            .eq("color", color)
        )
        for item in query.execute().data:
            specification = _clean(item.get("size")).upper()
            supabase.table("inventory_items").update({
                "sku_name": _build_sku_name(
                    category_name, brand, material, color, specification
                ),
                "category_id": category["id"],
                "brand_id": brand_map.get(brand),
                "model": (
                    specification
                    if category["specification_type"] == "model"
                    else None
                ),
            }).eq("id", item["id"]).execute()


def _validate_updates(
    edited_df, category_map, material_names=None, allow_duplicates=False,
):
    seen_keys = set()
    prepared = []
    for row in edited_df.to_dict("records"):
        if row.get("category") not in category_map:
            raise ValueError("请选择有效品类")
        category = category_map[row["category"]]
        material = _clean(row.get("material"))
        if (
            material and material_names is not None
            and material.casefold() not in material_names
        ):
            raise ValueError("请选择有效材质")
        specification = _specification(row, category)
        key = _normalized_key((
            category["name"], row.get("brand"), row.get("material"),
            row.get("color"), specification,
        ))
        if key in seen_keys and not allow_duplicates:
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


def _clean(value):
    return "" if pd.isna(value) else str(value).strip()


def _option_names(options):
    if options is None:
        return None
    return {
        _clean(value).casefold()
        for value in pd.DataFrame(options).get("name", [])
        if _clean(value)
    }
