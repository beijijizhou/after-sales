import re


HUMBIRD_PATTERN = re.compile(
    r"(?:SCGD-)?(B[A-Z0-9]{6})(?:-(\d+))?(?:-([AB]))?"
)


def matches(value):
    return HUMBIRD_PATTERN.fullmatch(value.strip().upper()) is not None


def build_candidates(value):
    value = value.strip().upper()

    if not value:
        return []

    match = HUMBIRD_PATTERN.fullmatch(value)
    if not match:
        return [value]

    order_code, sequence, variant = match.groups()
    prefix = f"SCGD-{order_code}"
    if variant:
        return [
            f"{prefix}-{sequence}-{variant}"
            if sequence else f"{prefix}-{variant}"
        ]
    if sequence:
        return [
            f"{prefix}-{sequence}-A",
            f"{prefix}-{sequence}-B",
        ]

    return [value]


def build_prefixes(value):
    value = value.strip().upper()
    match = HUMBIRD_PATTERN.fullmatch(value)
    if not match:
        return []

    order_code, sequence, variant = match.groups()
    if sequence or variant:
        return []
    return [f"SCGD-{order_code}-"]
