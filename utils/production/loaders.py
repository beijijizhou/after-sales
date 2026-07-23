from datetime import datetime, time, timedelta

import pandas as pd

from utils.production.constants import NY_TIMEZONE


def get_date_range(selected_date, snapshot_at=None):
    start_at = datetime.combine(selected_date, time.min, tzinfo=NY_TIMEZONE)
    end_at = datetime.combine(selected_date + timedelta(days=1), time.min, tzinfo=NY_TIMEZONE)
    if snapshot_at is not None and selected_date == snapshot_at.date():
        end_at = min(end_at, snapshot_at)
    return start_at.isoformat(), end_at.isoformat()


def load_daily_production_rows(supabase, selected_date, user_column, snapshot_at=None):
    start_at, end_at = get_date_range(selected_date, snapshot_at)
    rows = []
    page_size = 1000
    offset = 0

    while True:
        response = (
            supabase.table("barcode_scans")
            .select(f"id,barcode,{user_column},scanned_at,platform,multiple_count")
            .gte("scanned_at", start_at).lt("scanned_at", end_at)
            .order("scanned_at", desc=False)
            .order("id", desc=False)
            .range(offset, offset + page_size - 1).execute()
        )
        data = response.data
        rows.extend(data)
        if len(data) < page_size:
            break
        offset += page_size

    df = pd.DataFrame(rows)
    if "id" in df.columns:
        df = df.drop_duplicates(subset=["id"])
    return df


def load_summary_rpc(supabase, function_name, selected_date, snapshot_at=None):
    params = {"target_date": selected_date.isoformat()}
    if snapshot_at:
        params["snapshot_at"] = snapshot_at.isoformat()
    response = supabase.rpc(function_name, params).execute()
    return pd.DataFrame(response.data)


def get_rpc_name(user_column, qa_function, hotstamp_function):
    function_name_by_user_column = {
        "scanned_by": qa_function,
        "hotstamp_by": hotstamp_function,
    }
    return function_name_by_user_column.get(user_column)


def load_person_platform_summary_rows(supabase, selected_date, user_column, snapshot_at=None):
    function_name = get_rpc_name(
        user_column,
        "get_daily_qa_person_platform_summary",
        "get_daily_hotstamp_person_platform_summary",
    )
    return load_summary_rpc(supabase, function_name, selected_date, snapshot_at) if function_name else pd.DataFrame()


def load_hourly_summary_rows(supabase, selected_date, user_column, snapshot_at=None):
    function_name = get_rpc_name(
        user_column,
        "get_daily_qa_hourly_summary",
        "get_daily_hotstamp_hourly_summary",
    )
    return load_summary_rpc(supabase, function_name, selected_date, snapshot_at) if function_name else pd.DataFrame()


def load_hourly_person_client_rows(supabase, selected_date, user_column, snapshot_at=None):
    function_name = get_rpc_name(
        user_column,
        "get_daily_qa_hourly_person_client_summary",
        "get_daily_hotstamp_hourly_person_client_summary",
    )
    return load_summary_rpc(supabase, function_name, selected_date, snapshot_at) if function_name else pd.DataFrame()


def load_period_person_platform_rows(
    supabase, start_date, end_date, user_column, snapshot_at=None
):
    function_name = get_rpc_name(
        user_column,
        "get_period_qa_person_platform_summary",
        "get_period_hotstamp_person_platform_summary",
    )
    if not function_name:
        return pd.DataFrame()

    params = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
    if snapshot_at:
        params["snapshot_at"] = snapshot_at.isoformat()
    response = supabase.rpc(function_name, params).execute()
    return pd.DataFrame(response.data)
