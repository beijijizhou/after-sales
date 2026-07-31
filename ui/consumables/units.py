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
