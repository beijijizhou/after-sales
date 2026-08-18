"""Persist and query daily platform production consumption."""

import pandas as pd

from db.inventory.core.pagination import fetch_range_pages
from utils.erp.catalog import normalize_color
from utils.erp.inventory_mapping import normalize_size
from utils.erp.time_range import TIME_COLUMNS


def build_daily_platform_consumption(
    rows, department="DTF", category="彩色短袖",
):
    columns = ["business_date", "color", "size", "quantity", "record_count"]
    source = pd.DataFrame(rows).copy()
    required = {"部门", "品类", "颜色", "尺码", "数量"}
    if source.empty or not required.issubset(source.columns):
        return pd.DataFrame(columns=columns)
    source = source[
        source["部门"].eq(department)
        & source["品类"].eq(category)
    ].copy()
    timestamps = pd.Series(pd.NaT, index=source.index, dtype="datetime64[ns]")
    for column in TIME_COLUMNS:
        if column in source:
            timestamps = timestamps.fillna(
                pd.to_datetime(source[column], errors="coerce")
            )
    source["business_date"] = timestamps.dt.date
    source["color"] = source["颜色"].map(normalize_color)
    source["size"] = source["尺码"].map(normalize_size)
    source["quantity"] = pd.to_numeric(
        source["数量"], errors="coerce"
    ).fillna(0).clip(lower=0)
    source = source.dropna(subset=["business_date"])
    if source.empty:
        return pd.DataFrame(columns=columns)
    return source.groupby(
        ["business_date", "color", "size"], as_index=False
    ).agg(
        quantity=("quantity", "sum"),
        record_count=("quantity", "size"),
    )[columns]


def replace_daily_platform_consumption(
    supabase, department, category, platform, start_date, end_date,
    rows, source, operator="system",
):
    daily = build_daily_platform_consumption(rows, department, category)
    raw = pd.DataFrame(rows)
    colored = raw
    if {"部门", "品类"}.issubset(raw.columns):
        colored = raw[
            (raw["部门"] == department) & (raw["品类"] == category)
        ]
    if not colored.empty and daily.empty:
        raise ValueError(
            f"{platform} 返回了{category}数据，但缺少可用生产日期，未保存"
        )
    payload = daily.assign(
        business_date=daily["business_date"].astype(str),
        quantity=daily["quantity"].astype(int),
        record_count=daily["record_count"].astype(int),
    ).to_dict("records")
    return supabase.rpc("replace_platform_daily_consumption", {
        "p_department": department,
        "p_category": category,
        "p_platform": platform,
        "p_start_date": start_date.isoformat(),
        "p_end_date": end_date.isoformat(),
        "p_rows": payload,
        "p_source": source,
        "p_operator": operator,
    }).execute().data


def load_daily_platform_consumption(
    supabase, department, category, start_date, end_date,
):
    def fetch_page(first, last):
        return (
            supabase.table("production_platform_daily_consumption")
            .select("business_date,platform,color,size,quantity,record_count")
            .eq("department", department).eq("category", category)
            .gte("business_date", start_date.isoformat())
            .lte("business_date", end_date.isoformat())
            .order("business_date").order("platform")
            .range(first, last).execute().data or []
        )

    rows = fetch_range_pages(fetch_page, limit=None)
    return pd.DataFrame(rows)


def load_platform_sync_coverage(
    supabase, department, category, start_date, end_date,
):
    def fetch_page(first, last):
        return (
            supabase.table("production_consumption_sync_batches")
            .select("platform,start_date,end_date,status")
            .eq("status", "completed")
            .eq("department", department).eq("category", category)
            .gte("start_date", start_date.isoformat())
            .lte("end_date", end_date.isoformat())
            .order("start_date").order("platform")
            .range(first, last).execute().data or []
        )

    rows = fetch_range_pages(fetch_page, limit=None)
    coverage = {}
    for row in rows:
        first = pd.to_datetime(row.get("start_date"), errors="coerce")
        last = pd.to_datetime(row.get("end_date"), errors="coerce")
        if pd.isna(first) or pd.isna(last):
            continue
        coverage.setdefault(str(row.get("platform") or ""), set()).update(
            value.date() for value in pd.date_range(first, last, freq="D")
        )
    return coverage
