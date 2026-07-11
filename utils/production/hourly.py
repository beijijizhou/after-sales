import pandas as pd

from utils.production.constants import HALOO_PLATFORM, NY_TIMEZONE, OTHER_CLIENT
from utils.production.normalization import add_ny_hour, get_hour_range


def summarize_hourly_from_rpc(df, selected_date):
    required_columns = {"hour_start_at", "scan_count", "haloo_count"}
    if df.empty or not required_columns.issubset(df.columns):
        return pd.DataFrame()

    hourly_df = df.copy()
    hourly_df["hour"] = pd.to_datetime(hourly_df["hour_start_at"], errors="coerce", utc=True).dt.tz_convert(NY_TIMEZONE)
    hourly_df = hourly_df.dropna(subset=["hour"])
    hourly_df["scan_count"] = pd.to_numeric(hourly_df["scan_count"], errors="coerce").fillna(0).astype(int)
    hourly_df["haloo_count"] = pd.to_numeric(hourly_df["haloo_count"], errors="coerce").fillna(0).astype(int)
    hourly_df = hourly_df[["hour", "scan_count", "haloo_count"]]
    if hourly_df.empty:
        return pd.DataFrame()

    hourly_df = (
        pd.DataFrame({"hour": get_hour_range(hourly_df, selected_date)})
        .merge(hourly_df, on="hour", how="left")
        .fillna({"scan_count": 0, "haloo_count": 0})
    )
    hourly_df["scan_count"] = hourly_df["scan_count"].astype(int)
    hourly_df["haloo_count"] = hourly_df["haloo_count"].astype(int)
    hourly_df["haloo_percentage"] = (hourly_df["haloo_count"] / hourly_df["scan_count"] * 100).fillna(0)
    return hourly_df


def build_hourly_person_client_table(df):
    required_columns = {"hour_start_at", "person", "haloo_count", "other_count", "total_count"}
    if df.empty or not required_columns.issubset(df.columns):
        return pd.DataFrame()

    display_df = df.copy()
    display_df["hour"] = pd.to_datetime(display_df["hour_start_at"], errors="coerce", utc=True).dt.tz_convert(NY_TIMEZONE)
    display_df = display_df.dropna(subset=["hour"])
    display_df["小时"] = display_df["hour"].dt.strftime("%H:00")
    display_df["Haloo"] = pd.to_numeric(display_df["haloo_count"], errors="coerce").fillna(0).astype(int)
    display_df["小平台"] = pd.to_numeric(display_df["other_count"], errors="coerce").fillna(0).astype(int)
    display_df["总产量"] = pd.to_numeric(display_df["total_count"], errors="coerce").fillna(0).astype(int)
    display_df["Haloo 占比"] = (display_df["Haloo"] / display_df["总产量"] * 100).fillna(0).round(1)
    display_df["主要工作"] = display_df.apply(
        lambda row: HALOO_PLATFORM if row["Haloo"] >= row["小平台"] else OTHER_CLIENT,
        axis=1,
    )
    return build_hourly_people_rows(display_df)


def build_hourly_people_rows(display_df):
    hourly_rows = []
    for hour, hour_df in display_df.groupby("小时", sort=True):
        haloo_df = hour_df[hour_df["Haloo"] > 0]
        other_df = hour_df[hour_df["小平台"] > 0]
        haloo_count = int(hour_df["Haloo"].sum())
        other_count = int(hour_df["小平台"].sum())
        total_count = int(hour_df["总产量"].sum())
        hourly_rows.append({
            "小时": hour,
            "Haloo 人员": format_people(haloo_df, "Haloo"),
            "小平台人员": format_people(other_df, "小平台"),
            "Haloo": haloo_count,
            "小平台": other_count,
            "总产量": total_count,
            "Haloo 占比": round(haloo_count / total_count * 100, 1) if total_count else 0,
        })
    return pd.DataFrame(hourly_rows)


def format_people(rows, count_column):
    rows = rows.sort_values(count_column, ascending=False)
    return "\n".join(
        f"{row['person']} {int(row[count_column])}"
        for _, row in rows.iterrows()
        if int(row[count_column]) > 0
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
            haloo_count=("client", lambda values: (values == HALOO_PLATFORM).sum()),
        )
    )
    hourly_df = (
        pd.DataFrame({"hour": get_hour_range(df, selected_date)})
        .merge(hourly_df, on="hour", how="left")
        .fillna({"scan_count": 0, "haloo_count": 0})
    )
    hourly_df["scan_count"] = hourly_df["scan_count"].astype(int)
    hourly_df["haloo_count"] = hourly_df["haloo_count"].astype(int)
    hourly_df["haloo_percentage"] = (hourly_df["haloo_count"] / hourly_df["scan_count"] * 100).fillna(0)
    return hourly_df
