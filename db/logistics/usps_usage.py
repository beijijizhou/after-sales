from datetime import datetime, timezone

import pandas as pd


USAGE_COLUMNS = (
    "id,tenant_code,event_type,tracking_count,request_count,"
    "successful_count,failed_count,official_count,created_by,created_at"
)


def record_usps_usage(
    supabase,
    tracking_count,
    request_count,
    successful_count,
    failed_count,
    created_by,
    tenant_code="default",
):
    payload = {
        "tenant_code": tenant_code,
        "event_type": "query",
        "tracking_count": int(tracking_count),
        "request_count": int(request_count),
        "successful_count": int(successful_count),
        "failed_count": int(failed_count),
        "created_by": str(created_by or "system"),
    }
    return supabase.table("logistics_usps_usage_events").insert(payload).execute().data


def save_usps_usage_baseline(
    supabase, official_count, created_by, tenant_code="default"
):
    payload = {
        "tenant_code": tenant_code,
        "event_type": "baseline",
        "official_count": int(official_count),
        "created_by": str(created_by or "system"),
    }
    return supabase.table("logistics_usps_usage_events").insert(payload).execute().data


def load_usps_usage_events(
    supabase, start_at, tenant_code="default", limit=10000
):
    rows = (
        supabase.table("logistics_usps_usage_events")
        .select(USAGE_COLUMNS)
        .eq("tenant_code", tenant_code)
        .gte("created_at", start_at.astimezone(timezone.utc).isoformat())
        .order("created_at", desc=False)
        .limit(limit)
        .execute().data
    )
    return pd.DataFrame(rows)


def load_latest_usps_usage_baseline(
    supabase, start_at, tenant_code="default"
):
    rows = (
        supabase.table("logistics_usps_usage_events")
        .select(USAGE_COLUMNS)
        .eq("tenant_code", tenant_code)
        .eq("event_type", "baseline")
        .gte("created_at", start_at.astimezone(timezone.utc).isoformat())
        .order("created_at", desc=True)
        .limit(1)
        .execute().data
    )
    return rows[0] if rows else None


def utc_now():
    return datetime.now(timezone.utc)
