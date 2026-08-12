"""SKU group identity propagation, merge detection and metadata refresh."""

import pandas as pd


GROUP_COLUMNS = ["category", "brand", "material", "color"]


def propagate_sku_identity_changes(original_df, edited_df):
    originals = pd.DataFrame(original_df).copy()
    result = pd.DataFrame(edited_df).copy().set_index("id")
    for old_values, group in originals.groupby(
        GROUP_COLUMNS, dropna=False, sort=False
    ):
        old_group = tuple(clean(value) for value in old_values)
        group_ids = group["id"].tolist()
        changed_groups = {
            tuple(clean(row.get(column)) for column in GROUP_COLUMNS)
            for row in result.loc[group_ids].to_dict("records")
            if normalized_key(tuple(
                clean(row.get(column)) for column in GROUP_COLUMNS
            )) != normalized_key(old_group)
        }
        if len(changed_groups) == 1:
            new_group = next(iter(changed_groups))
            for column, value in zip(GROUP_COLUMNS, new_group):
                result.loc[group_ids, column] = value
    return result.reset_index()


def build_sku_identity_changes(original_df, edited_df):
    originals = pd.DataFrame(original_df).copy()
    edited = pd.DataFrame(edited_df).set_index("id")
    changes, changed_ids = [], set()
    for old_values, group in originals.groupby(
        GROUP_COLUMNS, dropna=False, sort=False
    ):
        group_ids = group["id"].tolist()
        final_groups = {
            tuple(clean(row.get(column)) for column in GROUP_COLUMNS)
            for row in edited.loc[group_ids].to_dict("records")
        }
        old_group = tuple(clean(value) for value in old_values)
        if len(final_groups) != 1:
            continue
        new_group = next(iter(final_groups))
        if normalized_key(old_group) == normalized_key(new_group):
            continue
        changes.append({
            **{
                f"old_{column}": value
                for column, value in zip(GROUP_COLUMNS, old_group)
            },
            **{
                f"new_{column}": value
                for column, value in zip(GROUP_COLUMNS, new_group)
            },
        })
        changed_ids.update(group_ids)
    return changes, changed_ids


def build_sku_merge_preview(original_df, edited_df):
    source = pd.DataFrame(original_df).copy()
    normalized = propagate_sku_identity_changes(original_df, edited_df)
    changes, _ = build_sku_identity_changes(source, normalized)
    previews = []
    for change in changes:
        old_values = tuple(change[f"old_{column}"] for column in GROUP_COLUMNS)
        new_values = tuple(change[f"new_{column}"] for column in GROUP_COLUMNS)
        old_rows = rows_matching_group(source, old_values)
        target_rows = rows_matching_group(source, new_values)
        if target_rows.empty:
            continue
        old_sizes = set(old_rows.get("规格", old_rows.get("size", [])).astype(str))
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


def refresh_changed_group_metadata(
    supabase, department_code, changes, category_map, brand_map,
    build_sku_name,
):
    for change in changes:
        category_name = change["new_category"]
        brand, material, color = (
            change["new_brand"], change["new_material"], change["new_color"]
        )
        category = category_map[category_name]
        rows = (
            supabase.table("inventory_items").select("id,size")
            .eq("department", department_code).eq("category", category_name)
            .eq("brand", brand).eq("material", material).eq("color", color)
            .execute().data
        )
        for item in rows:
            specification = clean(item.get("size")).upper()
            supabase.table("inventory_items").update({
                "sku_name": build_sku_name(
                    category_name, brand, material, color, specification
                ),
                "category_id": category["id"], "brand_id": brand_map.get(brand),
                "model": specification
                if category["specification_type"] == "model" else None,
            }).eq("id", item["id"]).execute()


def rows_matching_group(source, values):
    mask = pd.Series(True, index=source.index)
    for column, value in zip(GROUP_COLUMNS, values):
        actual = source[column].fillna("").astype(str).str.strip().str.casefold()
        mask &= actual.eq(clean(value).casefold())
    return source[mask]


def normalized_key(values):
    return tuple(clean(value).casefold() for value in values)


def clean(value):
    return "" if pd.isna(value) else str(value).strip()
