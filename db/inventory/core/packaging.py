import re


DEFAULT_BOX_UNITS = 72
MENS_BOX_UNITS = 100
BAG_UNITS_BY_SIZE = {
    "S": 300,
    "M": 300,
    "L": 300,
    "XL": 250,
    "2XL": 250,
    "3XL": 250,
    "4XL": 200,
    "5XL": 200,
}
DEFAULT_PACKAGING_RULES = {
    "standard_box": DEFAULT_BOX_UNITS,
    "mens_box": MENS_BOX_UNITS,
    "bag_s_l": 300,
    "bag_xl_3xl": 250,
    "bag_4xl_5xl": 200,
}

PACKAGING_COUNT_PATTERN = re.compile(r"(\d[\d,]*)\s*(箱|包)")


def get_units_per_package(brand, package_type, size, rules=None):
    rules = {**DEFAULT_PACKAGING_RULES, **(rules or {})}
    if package_type == "Box":
        key = "mens_box" if brand == "Men's" else "standard_box"
        return int(rules[key])
    if size in {"S", "M", "L"}:
        return int(rules["bag_s_l"])
    if size in {"XL", "2XL", "3XL"}:
        return int(rules["bag_xl_3xl"])
    return int(rules["bag_4xl_5xl"])


def get_default_box_units(brand):
    return MENS_BOX_UNITS if brand == "Men's" else DEFAULT_BOX_UNITS


def packaging_sku_key(brand, material, color, size, package_type):
    return tuple(
        str(value or "").strip()
        for value in [brand, material, color, size, package_type]
    )


def format_box_check(quantity, units_per_box):
    if quantity <= 0:
        return ""
    boxes, remainder = divmod(quantity, units_per_box)
    return f"{boxes}箱" if remainder == 0 else "混装"


def extract_packaging_summary(note):
    matches = PACKAGING_COUNT_PATTERN.findall(str(note or ""))
    return " + ".join(
        f"{int(number.replace(',', ''))}{package_type}"
        for number, package_type in matches
    )
