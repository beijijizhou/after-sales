def is_consumable_category(category):
    """Return whether an inventory selector represents consumables."""
    value = str(category or "").replace(" ", "").strip().lower()
    return "耗材" in value or value in {"consumable", "consumables"}
