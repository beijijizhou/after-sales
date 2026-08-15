"""Compatibility layer; SDS ERP calls live in its provider package."""

from automation.api.sds.shipments import (
    _parcel_rows,
    _qa_token,
    fetch_sds_pending_shipments,
)

__all__ = ["fetch_sds_pending_shipments"]
