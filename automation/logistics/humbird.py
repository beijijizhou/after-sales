"""Compatibility layer; Humbird ERP calls live in its provider package."""

from automation.api.humbird.shipments import (
    HUMBIRD_OPEN_LOGISTICS_PLATFORMS,
    HumbirdBrowserRefreshRequired,
    _stage_items,
    fetch_humbird_shipments,
    fetch_humbird_shipments_legacy,
    fetch_humbird_shipments_with_fallback,
)

__all__ = [
    "HUMBIRD_OPEN_LOGISTICS_PLATFORMS",
    "HumbirdBrowserRefreshRequired",
    "fetch_humbird_shipments",
    "fetch_humbird_shipments_legacy",
    "fetch_humbird_shipments_with_fallback",
]
