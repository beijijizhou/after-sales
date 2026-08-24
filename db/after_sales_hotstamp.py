"""Persistence and read models for the after-sales hotstamp-film audit."""

import pandas as pd


def import_hotstamp_film_batch(supabase, preview, operator):
    payload = {
        "p_source_file_id": preview["source_file_id"],
        "p_source_file_name": preview["source_file_name"],
        "p_source_url": preview.get("source_url") or "",
        "p_source_modified_at": preview.get("source_modified_at"),
        "p_source_hash": preview["source_hash"],
        "p_start_date": preview["start_date"],
        "p_end_date": preview["end_date"],
        "p_rows": preview["rows"],
        "p_invalid_row_count": preview.get("invalid_row_count", 0),
        "p_operator": operator or "system",
    }
    response = supabase.rpc(
        "import_after_sales_hotstamp_film_batch", payload
    ).execute()
    return (response.data or [{}])[0]


def load_hotstamp_film_comparison(supabase, start_date, end_date):
    response = supabase.rpc(
        "get_after_sales_hotstamp_film_comparison",
        {
            "p_start_date": start_date.isoformat(),
            "p_end_date": end_date.isoformat(),
        },
    ).execute()
    return pd.DataFrame(response.data)


def load_hotstamp_manual_analysis(supabase, start_date, end_date):
    payload = {
        "p_start_date": start_date.isoformat(),
        "p_end_date": end_date.isoformat(),
    }
    rows = []
    offset = 0
    while True:
        page = (
            supabase.rpc("get_after_sales_hotstamp_manual_analysis", payload)
            .range(offset, offset + 999)
            .execute()
            .data
        )
        rows.extend(page)
        if len(page) < 1000:
            break
        offset += 1000
    return pd.DataFrame(rows)


def load_hotstamp_film_batches(supabase, limit=100):
    response = (
        supabase.table("after_sales_hotstamp_film_sync_batches")
        .select(
            "id,source_file_id,source_file_name,source_url,source_modified_at,"
            "source_hash,start_date,end_date,row_count,total_film_quantity,"
            "invalid_row_count,operator,status,created_at"
        )
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return pd.DataFrame(response.data)


def load_hotstamp_film_batch_rows(supabase, batch_id):
    rows = []
    offset = 0
    while True:
        data = (
            supabase.table("after_sales_hotstamp_film_entries")
            .select(
                "business_date,source_sheet_name,source_row_number,"
                "source_platform,platform,cutting_person,matching_person,"
                "film_quantity,is_hoodie,multi_press_count,is_white_board,"
                "hotstamp_person,qa_person"
            )
            .eq("batch_id", batch_id)
            .order("business_date")
            .order("source_row_number")
            .range(offset, offset + 999)
            .execute()
            .data
        )
        rows.extend(data)
        if len(data) < 1000:
            break
        offset += 1000
    return pd.DataFrame(rows)
