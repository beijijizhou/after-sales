import pandas as pd


def package_size(item):
    unit = str(item.get("package_unit") or "").strip()
    size = pd.to_numeric(item.get("units_per_package"), errors="coerce")
    if unit != "箱" or pd.isna(size) or float(size) <= 0:
        return None
    return float(size)


def to_boxes(quantity, item):
    size = package_size(item)
    value = pd.to_numeric(quantity, errors="coerce")
    if size is None or pd.isna(value):
        return None
    return float(value) / size


def boxes_to_base(quantity, item):
    size = package_size(item)
    value = pd.to_numeric(quantity, errors="coerce")
    if size is None or pd.isna(value):
        return None
    return float(value) * size


def entry_unit(item):
    """Return the warehouse entry unit without inventing packaging."""
    return "箱" if package_size(item) is not None else str(
        item.get("base_unit") or "数量"
    ).strip()


def to_entry_quantity(quantity, item):
    """Convert stored base quantity to the unit used by the entry UI."""
    boxes = to_boxes(quantity, item)
    if boxes is not None:
        return boxes
    value = pd.to_numeric(quantity, errors="coerce")
    return None if pd.isna(value) else float(value)


def entry_to_base(quantity, item):
    """Convert UI quantity to base units; unpackaged SKUs already use base units."""
    value = pd.to_numeric(quantity, errors="coerce")
    if pd.isna(value):
        return None
    converted = boxes_to_base(value, item)
    return float(value) if converted is None else converted
