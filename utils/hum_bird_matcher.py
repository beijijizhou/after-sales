import re


def matches(value):
    return re.fullmatch(r"B[A-Z0-9]{6}-\d", value.strip().upper()) is not None


def build_candidates(value):
    value = value.strip().upper()

    if not value:
        return []

    if value.startswith("SCGD-"):
        base = value
    else:
        base = f"SCGD-{value}"

    if base.endswith("-A") or base.endswith("-B"):
        return [base]

    return [
        f"{base}-A",
        f"{base}-B",
    ]
