import pandas as pd

from utils.production_helpers import get_date_range, normalize_platform


def load_daily_platform_rows(supabase, selected_date, columns="platform"):
    start_at, end_at = get_date_range(selected_date)
    rows = []
    page_size = 1000
    offset = 0

    while True:
        query = (
            supabase
            .table("barcode_scans")
            .select(columns)
            .gte("scanned_at", start_at)
            .lt("scanned_at", end_at)
            .range(offset, offset + page_size - 1)
        )
        response = query.execute()
        data = response.data
        rows.extend(data)

        if len(data) < page_size:
            break

        offset += page_size

    return pd.DataFrame(rows)


def load_daily_platform_detail_rows(supabase, selected_date, platforms):
    frames = []
    for platform in platforms:
        df = load_daily_single_platform_rows(
            supabase,
            selected_date,
            platform
        )
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True).drop_duplicates()


def load_daily_single_platform_rows(supabase, selected_date, platform):
    start_at, end_at = get_date_range(selected_date)
    rows = []
    page_size = 1000
    offset = 0

    while True:
        response = (
            supabase
            .table("barcode_scans")
            .select("barcode,platform,scanned_at")
            .gte("scanned_at", start_at)
            .lt("scanned_at", end_at)
            .eq("platform", platform)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        data = response.data
        rows.extend(data)

        if len(data) < page_size:
            break

        offset += page_size

    return pd.DataFrame(rows)


def prepare_platform_rows(df):
    required_columns = {"platform"}
    if df.empty or not required_columns.issubset(df.columns):
        return pd.DataFrame()

    df = df.copy()
    df["platform"] = df["platform"].apply(normalize_platform)
    if "barcode" in df.columns:
        df["barcode"] = df["barcode"].astype(str).str.strip()
        df = df[df["barcode"] != ""]

    return df


def summarize_platform_counts(df):
    summary = df.groupby("platform", as_index=False).size()
    summary = summary.rename(columns={
        "platform": "平台",
        "size": "总数量",
    })
    total_count = int(summary["总数量"].sum())
    summary["占比"] = (
        summary["总数量"] / total_count * 100
    ).fillna(0).round(1)

    return summary.sort_values("总数量", ascending=False).reset_index(drop=True)


def build_platform_barcode_detail(df):
    if df.empty or not {"platform", "barcode", "scanned_at"}.issubset(df.columns):
        return pd.DataFrame()

    detail_df = df[["platform", "barcode", "scanned_at"]].rename(columns={
        "platform": "平台",
        "barcode": "条码",
        "scanned_at": "扫描时间",
    })

    return detail_df.sort_values(["平台", "扫描时间"], ascending=[True, True])
