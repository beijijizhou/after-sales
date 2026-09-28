import pandas as pd

from db.inventory.core.constants import SIZE_COLUMNS


def sort_sku_rows(
    rows,
    *,
    material="材质",
    style=None,
    color="颜色",
    size="尺码/型号",
    leading=None,
    leading_ascending=None,
    material_order=None,
    size_order=None,
):
    """Sort long-form SKU rows in the ERP's human review order."""
    result = pd.DataFrame(rows).copy()
    if result.empty:
        return result
    category = "品类" if "品类" in result else "category"
    if style is None:
        style = "款式" if material == "材质" else "style"
    requested_leading = list(leading or [])
    requested_ascending = list(
        leading_ascending or [True] * len(requested_leading)
    )
    requested_ascending.extend(
        [True] * (len(requested_leading) - len(requested_ascending))
    )
    leading_pairs = [
        (column, requested_ascending[index])
        for index, column in enumerate(requested_leading)
        if column in result
    ]
    sort_columns = [column for column, _ in leading_pairs]
    ascending = [direction for _, direction in leading_pairs]
    temporary = []

    # Hoodie users work with the two current standard products first.  This
    # is a pair-level priority: sorting material and style independently would
    # put every hooded variant before the regular crewneck.
    if {category, material, style}.issubset(result.columns):
        categories = {
            str(value).strip() for value in result[category]
            if pd.notna(value) and str(value).strip()
        }
        if categories == {"卫衣"}:
            normalized_material = (
                result[material].fillna("").astype(str).str.strip()
            )
            normalized_style = (
                result[style].fillna("").astype(str).str.strip()
            )
            result["_sku_hoodie_primary"] = 2
            result.loc[
                normalized_material.eq("连帽")
                & normalized_style.eq("常规"),
                "_sku_hoodie_primary",
            ] = 0
            result.loc[
                normalized_material.eq("圆领")
                & normalized_style.eq("常规"),
                "_sku_hoodie_primary",
            ] = 1
            sort_columns.append("_sku_hoodie_primary")
            ascending.append(True)
            temporary.append("_sku_hoodie_primary")

    for column, key in [
        (material, "_sku_material_order"),
        (style, "_sku_style_order"),
        (color, "_sku_color_order"),
    ]:
        if column not in result:
            continue
        normalized = result[column].fillna("").astype(str).str.strip()
        if column == material and material_order:
            order_key = f"{key}_business"
            result[order_key] = normalized.map(material_order).fillna(999)
            sort_columns.append(order_key)
            ascending.append(True)
            temporary.append(order_key)
        result[key] = normalized.str.casefold()
        sort_columns.append(key)
        ascending.append(True)
        temporary.append(key)

    if size in result:
        normalized_size = (
            result[size].fillna("").astype(str).str.strip().str.upper()
        )
        configured_size_order = size_order or {
            value: index for index, value in enumerate(SIZE_COLUMNS)
        }
        if not isinstance(configured_size_order, dict):
            configured_size_order = {
                value: index
                for index, value in enumerate(configured_size_order)
            }
        result["_sku_size_order"] = normalized_size.map(
            configured_size_order
        ).fillna(999)
        result["_sku_size_text"] = normalized_size.str.casefold()
        sort_columns.extend(["_sku_size_order", "_sku_size_text"])
        ascending.extend([True, True])
        temporary.extend(["_sku_size_order", "_sku_size_text"])

    if not sort_columns:
        return result.reset_index(drop=True)
    return (
        result.sort_values(
            sort_columns,
            ascending=ascending,
            kind="stable",
            na_position="last",
        )
        .drop(columns=temporary)
        .reset_index(drop=True)
    )
