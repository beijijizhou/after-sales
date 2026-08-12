from datetime import date
import re

import pandas as pd

from utils.google_sheets import values_for_range


DATE_TAB_PATTERN = re.compile(r"^\d{4}$")
UV_DETAIL_RANGE = "A1:K1200"


def load_monthly_sku_summary(
    sheets, spreadsheet_id, year, month,
    detail_range=UV_DETAIL_RANGE,
):
    daily_rows = []
    sku_totals = {}
    tabs = _list_month_tabs(sheets, spreadsheet_id, year, month)
    requested = [f"'{tab}'!{detail_range}" for _movement_date, tab in tabs]
    values_by_range = sheets.batch_get_values(spreadsheet_id, requested)
    for movement_date, tab in tabs:
        requested_range = f"'{tab}'!{detail_range}"
        values = values_for_range(values_by_range, tab, requested_range)
        summary, note = _parse_detail_summary_values(values)
        total_quantity = int(sum(summary.values()))
        daily_rows.append({
            "date": movement_date,
            "sheet_name": tab,
            "total_quantity": total_quantity,
            "range": detail_range,
            "status": "ok" if summary else "no_data",
            "note": note,
        })
        for sku, quantity in summary.items():
            sku_totals[sku] = sku_totals.get(sku, 0) + quantity
    daily_df = pd.DataFrame(daily_rows)
    if daily_df.empty:
        daily_df = pd.DataFrame(columns=[
            "date", "sheet_name", "total_quantity", "range", "status", "note",
        ])
    sku_df = pd.DataFrame([
        {"sku": sku, "total_quantity": quantity}
        for sku, quantity in sorted(sku_totals.items())
    ])
    missing_dates = _missing_month_dates(year, month, {day for day, _ in tabs})
    return daily_df, sku_df, missing_dates


def _parse_detail_summary_values(values):
    result = {}
    skipped_rows = 0
    for row in values:
        if len(row) < 10:
            continue
        material = str(row[4] or "").strip()
        progress = str(row[9] or "").strip()
        if not material or progress != "完成":
            if material or progress:
                skipped_rows += 1
            continue
        try:
            quantity = int(float(row[8] or 0))
        except (TypeError, ValueError):
            skipped_rows += 1
            continue
        if quantity <= 0:
            skipped_rows += 1
            continue
        result[material] = result.get(material, 0) + quantity
    note = "ok"
    if skipped_rows:
        note = f"ok;skipped_rows={skipped_rows}"
    return result, note


def _list_month_tabs(sheets, spreadsheet_id, year, month):
    tabs = []
    prefix = f"{month:02d}"
    for item in sheets.list_sheets(spreadsheet_id):
        title = str(item.get("title") or "").strip()
        if not DATE_TAB_PATTERN.fullmatch(title) or not title.startswith(prefix):
            continue
        tabs.append((_tab_date(title, year), title))
    return sorted(tabs)


def _tab_date(tab, year):
    return date(year, int(tab[:2]), int(tab[2:]))


def _missing_month_dates(year, month, existing_dates):
    month_start = date(year, month, 1)
    next_month = (
        date(year + 1, 1, 1)
        if month == 12 else date(year, month + 1, 1)
    )
    return [
        day for day in pd.date_range(month_start, next_month, inclusive="left")
        if day.date() not in existing_dates
    ]
