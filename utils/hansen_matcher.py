import re


HANSEN_ORDER_PATTERN = re.compile(r"LB\d{11}(?:[A-Z]\d+)?")


def matches(value):
    return HANSEN_ORDER_PATTERN.fullmatch(value.strip().upper()) is not None


def build_candidates(value):
    value = value.strip().upper()
    return [value] if value else []


def build_prefixes(value):
    value = value.strip().upper()
    return [f"{value},"] if matches(value) else []


def build_fuzzy_prefixes(value):
    value = value.strip().upper()
    return [value] if matches(value) else []


def extract_order_key(value):
    match = HANSEN_ORDER_PATTERN.search(str(value or "").upper())
    return match.group(0) if match else ""
