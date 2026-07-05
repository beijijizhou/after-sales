from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd


NY_TIMEZONE = ZoneInfo("America/New_York")
HALOO_PLATFORM = "Haloo"
OTHER_CLIENT = "小平台"
UNKNOWN_PLATFORM = "未标记平台"


def get_date_range(selected_date):
    start_at = datetime.combine(selected_date, time.min, tzinfo=NY_TIMEZONE)
    end_at = datetime.combine(selected_date, time.max, tzinfo=NY_TIMEZONE)

    return start_at.isoformat(), end_at.isoformat()


def load_daily_production_rows(supabase, selected_date, user_column):
    start_at, end_at = get_date_range(selected_date)
    rows = []
    page_size = 1000
    offset = 0

    while True:
        response = (
            supabase
            .table("barcode_scans")
            .select(f"barcode,{user_column},scanned_at,platform")
            .gte("scanned_at", start_at)
            .lte("scanned_at", end_at)
            .range(offset, offset + page_size - 1)
            .execute()
        )

        data = response.data
        rows.extend(data)
        if len(data) < page_size:
            break
        offset += page_size

    return pd.DataFrame(rows)


def normalize_platform(platform):
    platform = str(platform).strip()
    if not platform or platform.lower() in {"nan", "none", "null"}:
        return UNKNOWN_PLATFORM
    if platform.lower() == "haloo":
        return HALOO_PLATFORM
    return platform


def get_client(platform):
    if normalize_platform(platform) == HALOO_PLATFORM:
        return HALOO_PLATFORM
    return OTHER_CLIENT


def prepare_production_df(df, user_column):
    required_columns = {user_column, "platform", "barcode", "scanned_at"}
    if df.empty or not required_columns.issubset(df.columns):
        return pd.DataFrame()

    df = (
        df
        .dropna(subset=[user_column])
        .assign(**{
            user_column: lambda data: data[user_column].astype(str).str.strip(),
            "platform": lambda data: data["platform"].apply(normalize_platform),
            "client": lambda data: data["platform"].apply(get_client),
        })
    )
    return df[df[user_column] != ""]


def add_ny_hour(df):
    if df.empty or "scanned_at" not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df["scanned_at_ny"] = (
        pd.to_datetime(df["scanned_at"], errors="coerce", utc=True)
        .dt.tz_convert(NY_TIMEZONE)
    )
    df = df.dropna(subset=["scanned_at_ny"])
    df["hour"] = df["scanned_at_ny"].dt.floor("h")
    return df


def get_hour_range(df, selected_date):
    first_hour = df["hour"].min()
    last_hour = df["hour"].max()
    if selected_date == datetime.now(NY_TIMEZONE).date():
        last_hour = datetime.now(NY_TIMEZONE).replace(
            minute=0, second=0, microsecond=0
        )
    return pd.date_range(start=first_hour, end=last_hour, freq="h", tz=NY_TIMEZONE)


def get_working_hours(df):
    df = add_ny_hour(df)
    if df.empty:
        return 0

    start_at = df["scanned_at_ny"].min()
    end_at = df["scanned_at_ny"].max()
    hours = (end_at - start_at).total_seconds() / 3600

    return max(hours, 0)


def summarize_by_user(df, user_column):
    summary = df.groupby(user_column, as_index=False).size()
    summary = summary.rename(columns={user_column: "name", "size": "scan_count"})
    return summary.sort_values("scan_count", ascending=False).reset_index(drop=True)


def summarize_by_client(df):
    summary = df.groupby("client", as_index=False).size()
    summary = summary.rename(columns={"size": "scan_count"})
    return summary.sort_values("scan_count", ascending=False).reset_index(drop=True)


def build_person_platform_summary(df, user_column):
    pivot_df = (
        df
        .pivot_table(
            index=user_column, columns="platform", values="barcode",
            fill_value=0, aggfunc="size"
        )
        .reset_index()
        .rename(columns={user_column: "人员"})
    )
    platform_columns = [column for column in pivot_df.columns if column != "人员"]

    pivot_df["总生产数量"] = pivot_df[platform_columns].sum(axis=1)
    if HALOO_PLATFORM not in pivot_df.columns:
        pivot_df[HALOO_PLATFORM] = 0
    pivot_df["Haloo 数量"] = pivot_df[HALOO_PLATFORM]
    pivot_df["Haloo 占比"] = (
        pivot_df["Haloo 数量"] / pivot_df["总生产数量"] * 100
    ).fillna(0).round(1)
    detail_columns = [column for column in platform_columns if column != HALOO_PLATFORM]
    ordered_columns = ["人员", "总生产数量", "Haloo 数量", "Haloo 占比", *detail_columns]

    return (
        pivot_df[ordered_columns]
        .sort_values("Haloo 占比", ascending=False)
        .reset_index(drop=True)
    )


def summarize_by_hour(df, selected_date):
    df = add_ny_hour(df)
    if df.empty:
        return pd.DataFrame()

    hourly_df = (
        df
        .groupby("hour", as_index=False)
        .agg(
            scan_count=("barcode", "size"),
            haloo_count=("client", lambda values: (values == HALOO_PLATFORM).sum())
        )
    )
    hourly_df = (
        pd.DataFrame({"hour": get_hour_range(df, selected_date)})
        .merge(hourly_df, on="hour", how="left")
        .fillna({"scan_count": 0, "haloo_count": 0})
    )
    hourly_df["scan_count"] = hourly_df["scan_count"].astype(int)
    hourly_df["haloo_count"] = hourly_df["haloo_count"].astype(int)
    hourly_df["haloo_percentage"] = (
        hourly_df["haloo_count"] / hourly_df["scan_count"] * 100
    ).fillna(0)

    return hourly_df
