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
