"""Canonical cleanup and business ordering for selector values."""

import pandas as pd


def unique_values(values):
    """Return non-empty string values once, in alphabetical order."""
    return sorted({
        str(value).strip()
        for value in values
        if pd.notna(value) and str(value).strip()
    })


def ordered_values(values, preferred=(), *, include_missing=False):
    """Put available preferred values first, followed by remaining values."""
    available = set(unique_values(values))
    preferred_values = list(dict.fromkeys(
        preferred if include_missing else [
            value for value in preferred if value in available
        ]
    ))
    return [*preferred_values, *sorted(available - set(preferred_values))]
