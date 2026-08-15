from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from db.logistics.repository import SHIPMENT_COLUMNS, load_latest_label_reviews
from db.logistics.tracking_sources import load_tracking_check_sources


NEW_YORK = ZoneInfo("America/New_York")
CHECK_COLUMNS = (
    "id,tracking_number,checked_at,provider_status,has_postal_record,"
    "error_code,created_by"
)


def load_logistics_summary_data(supabase, start_date, end_date):
    start_at = datetime.combine(start_date, time.min, NEW_YORK).astimezone(timezone.utc)
    end_at = datetime.combine(
        end_date + timedelta(days=1), time.min, NEW_YORK
    ).astimezone(timezone.utc)
    shipments = _load_range(
        supabase, "logistics_shipments", SHIPMENT_COLUMNS,
        "last_seen_at", start_at, end_at,
    )
    checks = _load_range(
        supabase, "logistics_tracking_checks", CHECK_COLUMNS,
        "checked_at", start_at, end_at,
    )
    sources = load_tracking_check_sources(
        supabase, checks.get("id", pd.Series(dtype=str)).astype(str).tolist()
    )
    shipment_ids = list(dict.fromkeys([
        *shipments.get("id", pd.Series(dtype=str)).astype(str).tolist(),
        *sources.get("shipment_id", pd.Series(dtype=str)).astype(str).tolist(),
    ]))
    reviews = _load_reviews(supabase, shipment_ids)
    return shipments, checks, sources, reviews


def _load_range(
    supabase, table, columns, timestamp_column, start_at, end_at,
):
    rows = []
    for offset in range(0, 10000, 1000):
        page = (
            supabase.table(table).select(columns)
            .gte(timestamp_column, start_at.isoformat())
            .lt(timestamp_column, end_at.isoformat())
            .order(timestamp_column, desc=True)
            .range(offset, offset + 999).execute().data
        )
        rows.extend(page)
        if len(page) < 1000:
            break
    return pd.DataFrame(rows)


def _load_reviews(supabase, shipment_ids):
    frames = []
    for start in range(0, len(shipment_ids), 200):
        frame = load_latest_label_reviews(
            supabase, shipment_ids[start:start + 200]
        )
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates(
        "shipment_id", keep="first"
    )
