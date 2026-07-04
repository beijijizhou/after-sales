import re


def matches(value):
    return re.fullmatch(r"[A-Z0-9]{6}", value.strip().upper()) is not None


def build_candidates(value):
    value = value.strip().upper()

    if not value:
        return []

    if re.fullmatch(r"[A-Z0-9]{6}-\d", value):
        return [value]

    return [f"{value}-1"]
