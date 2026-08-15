from automation.api.hansen.client import fetch_hansen_production_records
from automation.api.hansen.config import load_hansen_credentials


def parse_hansen_records(records):
    # Kept lazy because shared catalog normalization imports Hansen's static
    # style map while the provider parser itself composes that shared core.
    from automation.api.hansen.parser import parse_hansen_records as parse

    return parse(records)

__all__ = [
    "fetch_hansen_production_records",
    "load_hansen_credentials",
    "parse_hansen_records",
]
