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

PACKAGING_COUNT_PATTERN = re.compile(r"(\d[\d,]*)\s*(箱|包)")


def get_units_per_package(brand, package_type, size):
    if package_type == "Box":
        return MENS_BOX_UNITS if brand == "Men's" else DEFAULT_BOX_UNITS
    return BAG_UNITS_BY_SIZE[size]


def get_default_box_units(brand):
    return MENS_BOX_UNITS if brand == "Men's" else DEFAULT_BOX_UNITS


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
