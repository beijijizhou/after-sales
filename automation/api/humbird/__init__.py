from automation.api.humbird.client import fetch_humbird_production_records
from automation.api.humbird.config import (
    load_humbird_credentials,
    load_humbird_credentials_with_local_refresh,
)
from automation.api.humbird.http_client import (
    HumbirdAuthenticationError,
    fetch_humbird_production_records_http,
)
from automation.api.humbird.payload import build_production_item_payload
from automation.api.humbird.open_client import (
    HumbirdOpenApiClient,
    HumbirdOpenApiError,
    fetch_open_production_records,
)
from automation.api.humbird.windowing import (
    is_result_limit_error,
    load_busy_day_chunks,
)
from automation.api.humbird.shipments import (
    HUMBIRD_LOGISTICS_PLATFORMS,
    HUMBIRD_OPEN_LOGISTICS_PLATFORMS,
    HUMBIRD_TOKEN_LOGISTICS_PLATFORMS,
    HumbirdBrowserRefreshRequired,
    fetch_humbird_shipments,
    fetch_humbird_shipments_legacy,
    fetch_humbird_shipments_with_fallback,
)
from automation.api.humbird.parser import parse_humbird_records


__all__ = [
    "build_production_item_payload",
    "fetch_humbird_production_records",
    "fetch_humbird_production_records_http",
    "HumbirdAuthenticationError",
    "load_humbird_credentials",
    "load_humbird_credentials_with_local_refresh",
    "HumbirdOpenApiClient",
    "HumbirdOpenApiError",
    "fetch_open_production_records",
    "is_result_limit_error",
    "load_busy_day_chunks",
    "HUMBIRD_LOGISTICS_PLATFORMS",
    "HUMBIRD_OPEN_LOGISTICS_PLATFORMS",
    "HUMBIRD_TOKEN_LOGISTICS_PLATFORMS",
    "HumbirdBrowserRefreshRequired",
    "fetch_humbird_shipments",
    "fetch_humbird_shipments_legacy",
    "fetch_humbird_shipments_with_fallback",
    "parse_humbird_records",
]
