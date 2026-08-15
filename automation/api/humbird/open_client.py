"""Compatibility imports for the standalone :mod:`humbird_erp` package."""

from humbird_erp.client import (
    HumbirdOpenApiClient,
    HumbirdOpenApiError,
    PAGE_SIZE,
    _date_range,
    _deduplicate,
    _enrich_record,
    _response_data,
    fetch_open_production_records,
)

__all__ = [
    "HumbirdOpenApiClient",
    "HumbirdOpenApiError",
    "PAGE_SIZE",
    "fetch_open_production_records",
]
