"""Inventory planning adapters and shared manual-outbound demand model."""

from db.inventory.planning.outbound_consumption import (
    OutboundConsumption,
    apparel_forecast_model,
    build_outbound_consumption_model,
    build_outbound_forecast_usage,
    load_outbound_consumption,
)

__all__ = [
    "OutboundConsumption",
    "apparel_forecast_model",
    "build_outbound_consumption_model",
    "build_outbound_forecast_usage",
    "load_outbound_consumption",
]
