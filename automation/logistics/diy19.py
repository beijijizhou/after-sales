"""Compatibility imports for 19DIY provider shipment APIs."""

from automation.api.diy19.shipments import (
    _absolute_url,
    _label_url,
    _list_form,
    _normalize_record,
    _request_headers,
    _tracking_numbers,
    fetch_diy19_shipments,
    load_diy19_logistics_credentials,
)

__all__ = ["fetch_diy19_shipments", "load_diy19_logistics_credentials"]
