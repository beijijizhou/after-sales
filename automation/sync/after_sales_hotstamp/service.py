"""Discover and preview weekly hotstamp-film workbooks from Drive."""

from automation.sync.after_sales_hotstamp.parser import (
    WEEKDAYS,
    fingerprint_rows,
    is_weekly_workbook,
    parse_daily_rows,
    parse_week_start,
)
from utils.google_sheets import values_for_range


DAILY_RANGE = "A1:I1000"


def load_hotstamp_film_previews(sheets, folder_id, progress=None):
    files = [
        item for item in sheets.list_spreadsheets_in_tree(folder_id)
        if is_weekly_workbook(item.get("name"))
    ]
    files.sort(key=lambda item: item["name"])
    previews = []
    for index, source in enumerate(files, start=1):
        if progress:
            progress(index, len(files), source["name"])
        previews.append(_load_workbook(sheets, source))
    return previews


def _load_workbook(sheets, source):
    week_start = parse_week_start(source["name"], source.get("createdTime"))
    available = {
        item["title"] for item in sheets.list_sheets(source["id"])
    }
    tabs = [name for name in WEEKDAYS if name in available]
    requested = [f"'{name}'!{DAILY_RANGE}" for name in tabs]
    values_by_range = sheets.batch_get_values(source["id"], requested)
    rows = []
    invalid_rows = []
    for day_index, tab in enumerate(WEEKDAYS):
        if tab not in tabs:
            continue
        cell_range = f"'{tab}'!{DAILY_RANGE}"
        values = values_for_range(values_by_range, tab, cell_range)
        parsed, invalid = parse_daily_rows(
            values, source, tab, week_start + _days(day_index)
        )
        rows.extend(parsed)
        invalid_rows.extend(invalid)
    return {
        "source_file_id": source["id"],
        "source_file_name": source["name"],
        "source_url": source.get("webViewLink") or "",
        "source_created_at": source.get("createdTime"),
        "source_modified_at": source.get("modifiedTime"),
        "start_date": week_start.isoformat(),
        "end_date": (week_start + _days(6)).isoformat(),
        "row_count": len(rows),
        "total_film_quantity": sum(row["film_quantity"] for row in rows),
        "invalid_row_count": len(invalid_rows),
        "invalid_rows": invalid_rows,
        "source_hash": fingerprint_rows(rows),
        "rows": rows,
    }


def _days(value):
    from datetime import timedelta

    return timedelta(days=value)
