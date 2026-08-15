"""Shared business stages for ERP logistics acquisition."""


UNACCEPTED = 1
IN_PRODUCTION = 2
SHIPPED = 6

STAGE_LABELS = {
    UNACCEPTED: "未接单",
    IN_PRODUCTION: "已接单（生产中）",
    SHIPPED: "已发货",
}
STAGE_OPTIONS = tuple(STAGE_LABELS.values())
STAGE_CODES = {label: code for code, label in STAGE_LABELS.items()}


def stage_label(code):
    return STAGE_LABELS.get(code, str(code))


__all__ = [
    "IN_PRODUCTION", "SHIPPED", "STAGE_CODES", "STAGE_LABELS",
    "STAGE_OPTIONS", "UNACCEPTED", "stage_label",
]
