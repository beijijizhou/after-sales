def is_consumable_category(category):
    """Return whether an inventory selector represents consumables."""
    value = str(category or "").replace(" ", "").strip().lower()
    return "耗材" in value or value in {"consumable", "consumables"}


def exclude_consumable_dimensions(dimensions):
    """Keep consumable master data out of production-inventory selectors."""
    if dimensions is None or dimensions.empty or "category" not in dimensions:
        return dimensions
    return dimensions[
        ~dimensions["category"].map(is_consumable_category)
    ].reset_index(drop=True)


def apply_phone_case_display_scope(rows, department, category):
    """Keep the large phone-case catalog out of the general UV table."""
    if rows is None or rows.empty or "category" not in rows:
        return rows
    if str(department or "").strip().upper() != "UV":
        return rows
    result = rows.copy()
    categories = result["category"].fillna("").astype(str).str.strip()
    if str(category or "").strip() == "手机壳":
        result = result[categories.eq("手机壳")]
        if "material" in result:
            result = result[
                result["material"].fillna("").astype(str).str.strip().ne("")
            ]
    else:
        result = result[categories.ne("手机壳")]
    return result.reset_index(drop=True)
