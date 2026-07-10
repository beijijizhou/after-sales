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


def load_hourly_summary_rows(supabase, selected_date, user_column, snapshot_at=None):
    function_name_by_user_column = {
        "scanned_by": "get_daily_qa_hourly_summary",
        "hotstamp_by": "get_daily_hotstamp_hourly_summary",
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


def load_hourly_person_client_rows(supabase, selected_date, user_column, snapshot_at=None):
    function_name_by_user_column = {
        "scanned_by": "get_daily_qa_hourly_person_client_summary",
        "hotstamp_by": "get_daily_hotstamp_hourly_person_client_summary",
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


def summarize_by_user_from_rpc(df):
    required_columns = {
        "person", "scan_count", "multiple_order_count",
        "first_scan_at", "last_scan_at",
    }
    if df.empty or not required_columns.issubset(df.columns):
        return pd.DataFrame()

    summary_df = df.copy()
    summary_df["scan_count"] = pd.to_numeric(summary_df["scan_count"], errors="coerce").fillna(0).astype(int)
    summary_df["multiple_order_count"] = (
        pd.to_numeric(summary_df["multiple_order_count"], errors="coerce").fillna(0).astype(int)
    )
    user_df = (
        summary_df
        .groupby("person", as_index=False)
        .agg(
            scan_count=("scan_count", "sum"),
            multiple_order_count=("multiple_order_count", "sum"),
            first_scan_at=("first_scan_at", "min"),
            last_scan_at=("last_scan_at", "max"),
        )
        .rename(columns={"person": "name"})
    )
    user_df["first_scan_at"] = pd.to_datetime(user_df["first_scan_at"], errors="coerce", utc=True)
    user_df["last_scan_at"] = pd.to_datetime(user_df["last_scan_at"], errors="coerce", utc=True)
    user_df["working_hours"] = (
        user_df["last_scan_at"] - user_df["first_scan_at"]
    ).dt.total_seconds() / 3600
    return user_df.sort_values("scan_count", ascending=False).reset_index(drop=True)


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
    hourly_df["haloo_percentage"] = (
        hourly_df["haloo_count"] / hourly_df["scan_count"] * 100
    ).fillna(0)
    return hourly_df


def build_hourly_person_client_table(df):
    required_columns = {"hour_start_at", "person", "haloo_count", "other_count", "total_count"}
    if df.empty or not required_columns.issubset(df.columns):
        return pd.DataFrame()

    display_df = df.copy()
    display_df["hour"] = pd.to_datetime(
        display_df["hour_start_at"], errors="coerce", utc=True
    ).dt.tz_convert(NY_TIMEZONE)
    display_df = display_df.dropna(subset=["hour"])
    display_df["小时"] = display_df["hour"].dt.strftime("%H:00")
    display_df["Haloo"] = pd.to_numeric(display_df["haloo_count"], errors="coerce").fillna(0).astype(int)
    display_df["小平台"] = pd.to_numeric(display_df["other_count"], errors="coerce").fillna(0).astype(int)
    display_df["总产量"] = pd.to_numeric(display_df["total_count"], errors="coerce").fillna(0).astype(int)
    display_df["Haloo 占比"] = (
        display_df["Haloo"] / display_df["总产量"] * 100
    ).fillna(0).round(1)
    display_df["主要工作"] = display_df.apply(
        lambda row: HALOO_PLATFORM if row["Haloo"] >= row["小平台"] else OTHER_CLIENT,
        axis=1,
    )

    def format_people(rows, count_column):
        rows = rows.sort_values(count_column, ascending=False)
        return "\n".join(
            f"{row['person']} {int(row[count_column])}"
            for _, row in rows.iterrows()
            if int(row[count_column]) > 0
        )

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


def build_person_switch_table(df):
    required_columns = {"hour_start_at", "person", "haloo_count", "other_count", "total_count"}
    if df.empty or not required_columns.issubset(df.columns):
        return pd.DataFrame()

    switch_df = df.copy()
    switch_df["hour"] = pd.to_datetime(
        switch_df["hour_start_at"], errors="coerce", utc=True
    ).dt.tz_convert(NY_TIMEZONE)
    switch_df = switch_df.dropna(subset=["hour"])
    switch_df["Haloo"] = pd.to_numeric(switch_df["haloo_count"], errors="coerce").fillna(0).astype(int)
    switch_df["小平台"] = pd.to_numeric(switch_df["other_count"], errors="coerce").fillna(0).astype(int)
    switch_df["总产量"] = pd.to_numeric(switch_df["total_count"], errors="coerce").fillna(0).astype(int)
    switch_df = switch_df[switch_df["总产量"] > 0]
    if switch_df.empty:
        return pd.DataFrame()

    switch_df["主要工作"] = switch_df.apply(
        lambda row: HALOO_PLATFORM if row["Haloo"] >= row["小平台"] else OTHER_CLIENT,
        axis=1,
    )
    switch_rows = []
    for person, person_df in switch_df.sort_values("hour").groupby("person", sort=False):
        work_path = person_df["主要工作"].tolist()
        compressed_path = []
        for work in work_path:
            if not compressed_path or compressed_path[-1] != work:
                compressed_path.append(work)

        period_rows = []
        current_work = None
        period_count = 0

        for _, row in person_df.sort_values("hour").iterrows():
            row_work = row["主要工作"]
            if current_work is None:
                current_work = row_work
            elif row_work != current_work:
                period_rows.append({
                    "work": current_work,
                    "count": period_count,
                })
                current_work = row_work
                period_count = 0

            if row_work == HALOO_PLATFORM:
                period_count += int(row["Haloo"])
            else:
                period_count += int(row["小平台"])

        if current_work is not None:
            period_rows.append({
                "work": current_work,
                "count": period_count,
            })

        period_detail = " -> ".join(
            f"{row['work']}（{row['count']}）"
            for row in period_rows
        )

        switch_count = max(len(compressed_path) - 1, 0)
        haloo_count = int(person_df["Haloo"].sum())
        other_count = int(person_df["小平台"].sum())
        sort_count = haloo_count + other_count
        if switch_count <= 2:
            risk = "正常"
        elif switch_count <= 4:
            risk = "注意"
        else:
            risk = "频繁切换"

        switch_rows.append({
            "人员": person,
            "切换次数": switch_count,
            "切换路径": period_detail,
            "风险": risk,
            "_sort_count": sort_count,
        })

    result_df = pd.DataFrame(switch_rows)
    return (
        result_df
        .sort_values(["切换次数", "_sort_count"], ascending=[False, False])
        .drop(columns=["_sort_count"])
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
