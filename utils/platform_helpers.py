import pandas as pd

from utils.production_helpers import NY_TIMEZONE, get_date_range, normalize_platform


def load_daily_platform_rows(supabase, selected_date, columns="platform"):
    start_at, end_at = get_date_range(selected_date)
    rows = []
    page_size = 1000
    offset = 0
    selected_columns = columns
    for stable_column in ["id", "scanned_at"]:
        if stable_column not in selected_columns.split(","):
            selected_columns = f"{stable_column},{selected_columns}"

    while True:
        query = (
            supabase
            .table("barcode_scans")
            .select(selected_columns)
            .gte("scanned_at", start_at)
            .lt("scanned_at", end_at)
            .order("scanned_at", desc=False)
            .order("id", desc=False)
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
            .select("id,barcode,platform,scanned_at,multiple_count")
            .gte("scanned_at", start_at)
            .lt("scanned_at", end_at)
            .eq("platform", platform)
            .order("scanned_at", desc=False)
            .order("id", desc=False)
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
    if "multiple_count" not in df.columns:
        df["multiple_count"] = 1
    df["multiple_count"] = (
        pd.to_numeric(df["multiple_count"], errors="coerce")
        .fillna(1)
        .clip(lower=1)
        .astype(int)
    )
    df["is_multiple_order"] = df["multiple_count"] > 1

    return df


def summarize_platform_counts(df):
    summary_df = df.copy()
    summary_df["scanned_at_ny"] = pd.to_datetime(
        summary_df["scanned_at"], errors="coerce", utc=True
    ).dt.tz_convert(NY_TIMEZONE)
    summary = (
        summary_df
        .groupby("platform", as_index=False)
        .agg(
            scan_count=("platform", "size"),
            multiple_order_count=("is_multiple_order", "sum"),
            last_scan_at=("scanned_at_ny", "max"),
        )
    )
    summary = summary.rename(columns={
        "platform": "平台",
        "scan_count": "总生产数量",
        "multiple_order_count": "多件订单数量",
        "last_scan_at": "最后扫描时间",
    })
    total_count = int(summary["总生产数量"].sum())
    summary["占比"] = (
        summary["总生产数量"] / total_count * 100
    ).fillna(0).round(1)
    summary["最后扫描时间"] = summary["最后扫描时间"].dt.strftime("%Y-%m-%d %H:%M:%S")

    return summary.sort_values("总生产数量", ascending=False).reset_index(drop=True)


def build_latest_platform_barcodes(df, limit=10):
    required_columns = {"platform", "barcode", "scanned_at"}
    if df.empty or not required_columns.issubset(df.columns):
        return pd.DataFrame(columns=["平台", "条码", "扫描时间"])

    latest_df = df.copy()
    latest_df["scanned_at_ny"] = pd.to_datetime(
        latest_df["scanned_at"], errors="coerce", utc=True
    ).dt.tz_convert(NY_TIMEZONE)
    latest_df = latest_df.dropna(subset=["scanned_at_ny"])
    latest_df = latest_df.sort_values(["platform", "scanned_at_ny"], ascending=[True, False])
    latest_df = latest_df.groupby("platform", as_index=False, group_keys=False).head(limit)
    display_df = latest_df[["platform", "barcode", "scanned_at_ny"]].rename(columns={
        "platform": "平台",
        "barcode": "条码",
        "scanned_at_ny": "扫描时间",
    })
    display_df["扫描时间"] = display_df["扫描时间"].dt.strftime("%H:%M:%S")
    return display_df.sort_values(["平台", "扫描时间"], ascending=[True, False]).reset_index(drop=True)


def build_platform_barcode_detail(df):
    required_columns = {"platform", "barcode", "scanned_at", "multiple_count"}
    if df.empty or not required_columns.issubset(df.columns):
        return pd.DataFrame()

    detail_df = df[["platform", "barcode", "multiple_count", "scanned_at"]].rename(columns={
        "platform": "平台",
        "barcode": "条码",
        "multiple_count": "multiple_count",
        "scanned_at": "扫描时间",
    })

    return detail_df.sort_values(["平台", "扫描时间"], ascending=[True, True])
