"""Shared helpers for interpreting Google Sheets API responses."""


def values_for_range(values_by_range, sheet_name, requested_range):
    """Return values for a requested range despite API range normalization."""
    if requested_range in values_by_range:
        return values_by_range[requested_range]

    range_suffix = requested_range.split("!", 1)[1]
    for returned_range, values in values_by_range.items():
        normalized_range = returned_range.strip("'")
        if normalized_range.startswith(f"{sheet_name}'!") or (
            returned_range.endswith(range_suffix)
            and sheet_name in returned_range
        ):
            return values
    return []
