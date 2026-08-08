import pandas as pd

from db.inventory.core.constants import SIZE_COLUMNS


def sort_sku_rows(
    rows,
    *,
    material="材质",
    color="颜色",
    size="尺码/型号",
    leading=None,
    leading_ascending=None,
):
    """Sort long-form SKU rows in the ERP's human review order."""
    result = pd.DataFrame(rows).copy()
    if result.empty:
        return result
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

    for column, key in [
        (material, "_sku_material_order"),
        (color, "_sku_color_order"),
    ]:
        if column not in result:
            continue
        result[key] = result[column].fillna("").astype(str).str.strip().str.casefold()
        sort_columns.append(key)
        ascending.append(True)
        temporary.append(key)

    if size in result:
        normalized_size = (
            result[size].fillna("").astype(str).str.strip().str.upper()
        )
        size_order = {value: index for index, value in enumerate(SIZE_COLUMNS)}
        result["_sku_size_order"] = normalized_size.map(size_order).fillna(999)
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
