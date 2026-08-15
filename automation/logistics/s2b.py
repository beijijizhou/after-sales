"""Compatibility layer; S2B ERP calls live in its provider package."""

from automation.api.s2b.shipments import (
    PENDING_STATUS,
    S2BAuthenticationError,
    _normalize_order,
    _order_payload,
    fetch_s2b_label,
    fetch_s2b_pending_shipments,
)

__all__ = [
    "PENDING_STATUS",
    "S2BAuthenticationError",
    "fetch_s2b_label",
    "fetch_s2b_pending_shipments",
]
