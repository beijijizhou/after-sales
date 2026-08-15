"""USPS querying, caching, and audit persistence."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from automation.logistics import (
    USPSClient,
    classify_usps_response,
    load_usps_credentials,
)
from db.logistics import (
    load_latest_tracking_checks,
    save_tracking_checks,
    save_tracking_check_sources,
)
from db.logistics.usps_usage import record_usps_usage
from utils.auth import get_current_operator_name


def query_usps(
    numbers, supabase=None, database_error=None, source_shipments=None,
):
    if not numbers:
        return []
    batches = []
    try:
        credentials = load_usps_credentials(st.secrets)
        client = USPSClient(
            credentials["client_id"], credentials["client_secret"]
        )
        batches = [numbers[start:start + 35] for start in range(0, len(numbers), 35)]
        with ThreadPoolExecutor(max_workers=min(4, len(batches))) as executor:
            responses = list(executor.map(client.track, batches))
        rows = [
            classify_usps_response(item)
            for response in responses for item in response
        ]
        returned = {row["tracking_number"] for row in rows}
        rows.extend(
            failed_tracking_row(number, "USPS_NO_RESPONSE")
            for number in numbers if number not in returned
        )
        _save_tracking_results(
            supabase, rows, database_error, source_shipments
        )
        failed_count = sum(bool(row.get("error_code")) for row in rows)
        _record_usage(
            supabase, len(numbers), len(batches),
            len(rows) - failed_count, failed_count, database_error,
        )
        return rows
    except Exception as error:
        failure_rows = [
            failed_tracking_row(number, type(error).__name__)
            for number in numbers
        ]
        _save_tracking_results(
            supabase, failure_rows, database_error, source_shipments
        )
        _record_usage(
            supabase, len(numbers), len(batches), 0, len(numbers), database_error
        )
        st.error(f"USPS 接口查询失败：{error}")
        return None


def tracking_query_plan(supabase, numbers, force_usps, database_error=None):
    if supabase is None:
        return pd.DataFrame(), list(numbers)
    try:
        latest = load_latest_tracking_checks(supabase, numbers)
    except Exception as error:
        st.warning("数据库历史查询暂时不可用，本次将直接请求USPS。")
        if database_error:
            st.caption(database_error(error))
        return pd.DataFrame(), list(numbers)
    return split_tracking_cache(numbers, latest, force_usps)


def failed_tracking_row(tracking_number, error_code):
    return {
        "tracking_number": str(tracking_number),
        "provider_status": "",
        "has_postal_record": False,
        "has_pre_scan": False,
        "response_payload": {},
        "error_code": str(error_code or "USPS_QUERY_FAILED"),
        "cache_expires_at": (
            datetime.now(timezone.utc) + timedelta(minutes=5)
        ).isoformat(),
    }


def split_tracking_cache(numbers, latest, force_usps=False):
    if force_usps or latest.empty:
        return pd.DataFrame(), list(numbers)
    frame = latest.copy()
    expiry = pd.to_datetime(frame["cache_expires_at"], errors="coerce", utc=True)
    fresh = frame[expiry > datetime.now(timezone.utc)]
    cached_numbers = set(fresh["tracking_number"].astype(str))
    pending = [number for number in numbers if number not in cached_numbers]
    return fresh, pending


def _save_tracking_results(
    supabase, rows, database_error=None, source_shipments=None,
):
    if supabase is None or not rows:
        return
    try:
        saved = save_tracking_checks(
            supabase, rows, get_current_operator_name()
        )
        save_tracking_check_sources(supabase, saved, source_shipments)
    except Exception as error:
        st.warning("USPS查询已完成，但Tracking响应未能写入数据库。")
        if database_error:
            st.caption(database_error(error))


def _record_usage(
    supabase, tracking_count, request_count, successful_count, failed_count,
    database_error,
):
    if supabase is None:
        return
    try:
        record_usps_usage(
            supabase, tracking_count, request_count,
            successful_count, failed_count, get_current_operator_name(),
        )
    except Exception as error:
        st.warning("USPS查询已完成，但本次用量未能写入统计表。")
        if database_error:
            st.caption(database_error(error))
