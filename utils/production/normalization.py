from datetime import datetime

import pandas as pd

from utils.production.constants import HALOO_PLATFORM, NY_TIMEZONE, OTHER_CLIENT, UNKNOWN_PLATFORM


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

    hours = (df["scanned_at_ny"].max() - df["scanned_at_ny"].min()).total_seconds() / 3600
    return max(hours, 0)


def get_person_working_hours(df, user_column):
    df = add_ny_hour(df)
    if df.empty:
        return pd.DataFrame(columns=[user_column, "working_hours"])

    summary = df.groupby(user_column)["scanned_at_ny"].agg(["min", "max"]).reset_index()
    summary["working_hours"] = (summary["max"] - summary["min"]).dt.total_seconds() / 3600
    return summary[[user_column, "working_hours"]]
