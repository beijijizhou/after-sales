import re


HUMBIRD_PATTERN = re.compile(
    r"(?:SCGD-)?(B[A-Z0-9]{6})(?:-(\d+))?(?:-([AB]))?"
)
EMBEDDED_PATTERN = re.compile(
    r"(?:SCGD-|^)(B[A-Z0-9]{6})(?=-|$)(?:-(\d+))?(?:-([AB]))?"
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


def order_code(value):
    match = HUMBIRD_PATTERN.fullmatch(value.strip().upper())
    return match.group(1) if match else ""


def embedded_order_codes(barcode):
    return [
        found.group(1)
        for found in EMBEDDED_PATTERN.finditer(str(barcode or "").upper())
    ]


def matches_embedded(barcode, value):
    """Whether a malformed scan payload carries the searched order item."""
    match = HUMBIRD_PATTERN.fullmatch(value.strip().upper())
    if not match:
        return False
    code, sequence, variant = match.groups()
    for found in EMBEDDED_PATTERN.finditer(str(barcode or "").upper()):
        found_code, found_sequence, found_variant = found.groups()
        if found_code != code:
            continue
        if sequence and int(sequence) != int(found_sequence or -1):
            continue
        if variant and variant != found_variant:
            continue
        return True
    return False
