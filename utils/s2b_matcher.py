import re


ORDER_PATTERN = re.compile(r"([A-Z0-9]{6})(?:-(\d+))?")
EMBEDDED_PATTERN = re.compile(r"([A-Z0-9]{6})-(\d+)$")


def matches(value):
    return re.fullmatch(r"[A-Z0-9]{6}", value.strip().upper()) is not None


def build_candidates(value):
    value = value.strip().upper()

    if not value:
        return []

    if re.fullmatch(r"[A-Z0-9]{6}-\d+", value):
        return [value]

    return [value]


def build_prefixes(value):
    value = value.strip().upper()
    if not matches(value):
        return []
    return [f"{value}-"]


def order_code(value):
    match = ORDER_PATTERN.fullmatch(value.strip().upper())
    return match.group(1) if match else ""


def embedded_order_codes(barcode):
    found = EMBEDDED_PATTERN.search(str(barcode or "").upper())
    return [found.group(1)] if found else []


def matches_embedded(barcode, value):
    """Whether a malformed scan payload ends with the searched order item."""
    match = ORDER_PATTERN.fullmatch(value.strip().upper())
    found = EMBEDDED_PATTERN.search(str(barcode or "").upper())
    if not match or not found:
        return False
    code, item = match.groups()
    if found.group(1) != code:
        return False
    return not item or int(item) == int(found.group(2))
