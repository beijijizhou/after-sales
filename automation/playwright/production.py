"""Compatibility exports for the former Playwright-only dispatcher."""

from automation.production import (
    DIAGNOSTIC_PATH,
    PLATFORMS_BY_DEPARTMENT,
    PRODUCTION_DEPARTMENTS,
    PRODUCTION_PLATFORM_NAMES,
    ProductionLoginRequired,
    SDS_PLATFORM_PROFILES,
    load_production_data,
)


__all__ = [
    "DIAGNOSTIC_PATH",
    "PLATFORMS_BY_DEPARTMENT",
    "PRODUCTION_DEPARTMENTS",
    "PRODUCTION_PLATFORM_NAMES",
    "ProductionLoginRequired",
    "SDS_PLATFORM_PROFILES",
    "load_production_data",
]
