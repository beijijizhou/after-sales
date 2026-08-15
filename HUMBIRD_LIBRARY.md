# Humbird ERP Python Library

`humbird-erp` is the dependency-light client used by this project to access
the official Humbird Open Platform. It has no Streamlit, Supabase, browser, or
project database dependency.

## Install from this repository

```bash
python -m pip install .
```

## Usage

```python
from datetime import date

from humbird_erp import HumbirdClient

client = HumbirdClient({"api_key": "your-api-key"})

items = client.production_items(
    date(2026, 8, 1),
    date(2026, 8, 1),
)
product = client.product("spu-id")
waybill = client.waybill("order-number")
```

The client sends the key through the `x-api-key` header. Do not commit API
keys or include them in logs. Production-item queries use New York day
boundaries, accept a maximum 30-day range, read every page, verify the provider
total, and deduplicate by production-item code.

`fetch_production_records` is a convenience function that also hydrates color
and size from product details. `HumbirdApiError` is raised for gateway,
authorization, rate-limit, and provider response errors.

## Application adapters

The host ERP keeps credential loading, encrypted legacy tokens, fallback
behavior, provider-specific normalization, and database auditing under
`automation/api/humbird/`. Those concerns intentionally stay outside this
library so it can be reused by another application.
