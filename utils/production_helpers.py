from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd


NY_TIMEZONE = ZoneInfo("America/New_York")
HALOO_PLATFORM = "Haloo"
OTHER_CLIENT = "小平台"
UNKNOWN_PLATFORM = "未标记平台"


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


def load_person_platform_summary_rows(supabase, selected_date, user_column, snapshot_at=None):
    function_name_by_user_column = {
        "scanned_by": "get_daily_qa_person_platform_summary",
        "hotstamp_by": "get_daily_hotstamp_person_platform_summary",
    }
    function_name = function_name_by_user_column.get(user_column)
    if function_name is None:
        return pd.DataFrame()

    response = (
        supabase
        .rpc(
            function_name,
            {
                "target_date": selected_date.isoformat(),
                "snapshot_at": snapshot_at.isoformat() if snapshot_at else None,
            }
        )
        .execute()
    )
    return pd.DataFrame(response.data)


def normalize_platform(platform):
    platform = str(platform).strip()
    if not platform or platform.lower() in {"nan", "none", "null"}:
        return UNKNOWN_PLATFORM
    if platform.lower() == "haloo":
        return HALOO_PLATFORM
    return platform


def get_client(platform):
    return HALOO_PLATFORM if normalize_platform(platform) == HALOO_PLATFORM else OTHER_CLIENT


def prepare_production_df(df, user_column):
    required_columns = {user_column, "platform", "barcode", "scanned_at"}
    if df.empty or not required_columns.issubset(df.columns):
        return pd.DataFrame()

    df = df.dropna(subset=[user_column]).assign(**{
        user_column: lambda data: data[user_column].astype(str).str.strip(),
        "platform": lambda data: data["platform"].apply(normalize_platform),
        "client": lambda data: data["platform"].apply(get_client),
    })
    if "multiple_count" not in df.columns:
        df["multiple_count"] = 1
    df["multiple_count"] = pd.to_numeric(
        df["multiple_count"], errors="coerce"
    ).fillna(1).clip(lower=1).astype(int)
    df["is_multiple_order"] = df["multiple_count"] > 1
    return df[df[user_column] != ""]


def add_ny_hour(df):
    if df.empty or "scanned_at" not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df["scanned_at_ny"] = pd.to_datetime(
        df["scanned_at"], errors="coerce", utc=True
    ).dt.tz_convert(NY_TIMEZONE)
    df = df.dropna(subset=["scanned_at_ny"])
    df["hour"] = df["scanned_at_ny"].dt.floor("h")
    return df


def get_hour_range(df, selected_date):
    first_hour = df["hour"].min()
    last_hour = df["hour"].max()
    if selected_date == datetime.now(NY_TIMEZONE).date():
        last_hour = datetime.now(NY_TIMEZONE).replace(minute=0, second=0, microsecond=0)
    return pd.date_range(start=first_hour, end=last_hour, freq="h", tz=NY_TIMEZONE)


def get_working_hours(df):
    df = add_ny_hour(df)
    if df.empty:
        return 0

    hours = (
        df["scanned_at_ny"].max() - df["scanned_at_ny"].min()
    ).total_seconds() / 3600
    return max(hours, 0)


def get_person_working_hours(df, user_column):
    df = add_ny_hour(df)
    if df.empty:
        return pd.DataFrame(columns=[user_column, "working_hours"])

    summary = df.groupby(user_column)["scanned_at_ny"].agg(["min", "max"]).reset_index()
    summary["working_hours"] = (
        summary["max"] - summary["min"]
    ).dt.total_seconds() / 3600
    return summary[[user_column, "working_hours"]]


def summarize_by_user(df, user_column):
    summary = (
        df
        .groupby(user_column, as_index=False)
        .agg(
            scan_count=("barcode", "size"),
            multiple_order_count=("is_multiple_order", "sum")
        )
        .rename(columns={user_column: "name"})
    )
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
    multiple_orders = df.groupby(user_column, as_index=False)["is_multiple_order"].sum()
    multiple_orders = multiple_orders.rename(
        columns={user_column: "人员", "is_multiple_order": "多件订单数量"}
    )
    pivot_df = pivot_df.merge(multiple_orders, on="人员", how="left")
    working_hours = get_person_working_hours(df, user_column)
    pivot_df = pivot_df.merge(
        working_hours.rename(columns={user_column: "人员"}), on="人员", how="left"
    )
    pivot_df["时产量"] = (
        pivot_df["总生产数量"] / pivot_df["working_hours"]
    ).replace([float("inf"), -float("inf")], 0).fillna(0).round(1)
    if HALOO_PLATFORM not in pivot_df.columns:
        pivot_df[HALOO_PLATFORM] = 0
    pivot_df["Haloo 数量"] = pivot_df[HALOO_PLATFORM]
    pivot_df["Haloo 占比"] = (
        pivot_df["Haloo 数量"] / pivot_df["总生产数量"] * 100
    ).fillna(0).round(1)
    detail_columns = [column for column in platform_columns if column != HALOO_PLATFORM]
    ordered_columns = [
        "人员", "总生产数量", "多件订单数量", "时产量",
        "Haloo 数量", "Haloo 占比", *detail_columns,
    ]

    return (
        pivot_df[ordered_columns]
        .sort_values("Haloo 占比", ascending=False)
        .reset_index(drop=True)
    )


def build_person_platform_summary_from_rpc(df):
    required_columns = {
        "person", "platform", "scan_count", "multiple_order_count",
        "first_scan_at", "last_scan_at",
    }
    if df.empty or not required_columns.issubset(df.columns):
        return pd.DataFrame()

    summary_df = df.copy()
    summary_df["platform"] = summary_df["platform"].apply(normalize_platform)
    summary_df["scan_count"] = pd.to_numeric(summary_df["scan_count"], errors="coerce").fillna(0).astype(int)
    summary_df["multiple_order_count"] = (
        pd.to_numeric(summary_df["multiple_order_count"], errors="coerce").fillna(0).astype(int)
    )
    pivot_df = (
        summary_df
        .pivot_table(
            index="person",
            columns="platform",
            values="scan_count",
            fill_value=0,
            aggfunc="sum",
        )
        .reset_index()
        .rename(columns={"person": "人员"})
    )
    platform_columns = [column for column in pivot_df.columns if column != "人员"]
    pivot_df["总生产数量"] = pivot_df[platform_columns].sum(axis=1)

    multiple_orders = (
        summary_df
        .groupby("person", as_index=False)["multiple_order_count"]
        .sum()
        .rename(columns={"person": "人员", "multiple_order_count": "多件订单数量"})
    )
    pivot_df = pivot_df.merge(multiple_orders, on="人员", how="left")

    time_df = summary_df.copy()
    time_df["first_scan_at"] = pd.to_datetime(time_df["first_scan_at"], errors="coerce", utc=True)
    time_df["last_scan_at"] = pd.to_datetime(time_df["last_scan_at"], errors="coerce", utc=True)
    working_hours = (
        time_df
        .groupby("person", as_index=False)
        .agg(first_scan_at=("first_scan_at", "min"), last_scan_at=("last_scan_at", "max"))
    )
    working_hours["working_hours"] = (
        working_hours["last_scan_at"] - working_hours["first_scan_at"]
    ).dt.total_seconds() / 3600
    pivot_df = pivot_df.merge(
        working_hours.rename(columns={"person": "人员"})[["人员", "working_hours"]],
        on="人员",
        how="left",
    )
    pivot_df["时产量"] = (
        pivot_df["总生产数量"] / pivot_df["working_hours"]
    ).replace([float("inf"), -float("inf")], 0).fillna(0).round(1)

    if HALOO_PLATFORM not in pivot_df.columns:
        pivot_df[HALOO_PLATFORM] = 0
    pivot_df["Haloo 数量"] = pivot_df[HALOO_PLATFORM]
    pivot_df["Haloo 占比"] = (
        pivot_df["Haloo 数量"] / pivot_df["总生产数量"] * 100
    ).fillna(0).round(1)

    detail_columns = [column for column in platform_columns if column != HALOO_PLATFORM]
    ordered_columns = [
        "人员", "总生产数量", "多件订单数量", "时产量",
        "Haloo 数量", "Haloo 占比", *detail_columns,
    ]
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
