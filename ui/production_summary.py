from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

NY_TIMEZONE = ZoneInfo("America/New_York")


def get_date_range(selected_date):
    start_at = datetime.combine(
        selected_date,
        time.min,
        tzinfo=NY_TIMEZONE
    ).isoformat()
    end_at = datetime.combine(
        selected_date,
        time.max,
        tzinfo=NY_TIMEZONE
    ).isoformat()

    return start_at, end_at


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

        rows.extend(response.data)

        if len(response.data) < page_size:
            break

        offset += page_size

    return pd.DataFrame(rows)


def get_client(platform):
    platform = str(platform).strip().lower()

    if platform == "haloo":
        return "Haloo"

    return "小平台"


def prepare_production_df(df, user_column):
    if df.empty or user_column not in df.columns or "platform" not in df.columns:
        return pd.DataFrame()

    df = (
        df
        .dropna(subset=[user_column])
        .assign(**{
            user_column: lambda data: data[user_column].astype(str).str.strip(),
            "client": lambda data: data["platform"].apply(get_client),
        })
    )
    df = df[df[user_column] != ""]

    return df


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


def summarize_by_user(df, user_column):
    return (
        df
        .groupby(user_column, as_index=False)
        .size()
        .rename(columns={
            user_column: "name",
            "size": "scan_count",
        })
        .sort_values("scan_count", ascending=False)
        .reset_index(drop=True)
    )


def summarize_by_client(df):
    return (
        df
        .groupby("client", as_index=False)
        .size()
        .rename(columns={"size": "scan_count"})
        .sort_values("scan_count", ascending=False)
        .reset_index(drop=True)
    )


def summarize_by_user_and_client(df, user_column):
    return (
        df
        .groupby([user_column, "client"], as_index=False)
        .size()
        .rename(columns={
            user_column: "name",
            "size": "scan_count",
        })
        .sort_values(["name", "scan_count"], ascending=[True, False])
        .reset_index(drop=True)
    )


def summarize_by_hour(df, selected_date):
    df = add_ny_hour(df)
    if df.empty:
        return pd.DataFrame()

    first_hour = df["hour"].min()
    today = datetime.now(NY_TIMEZONE).date()

    if selected_date == today:
        last_hour = datetime.now(NY_TIMEZONE).replace(
            minute=0,
            second=0,
            microsecond=0
        )
    else:
        last_hour = df["hour"].max()

    hourly_df = (
        df
        .groupby("hour", as_index=False)
        .agg(
            scan_count=("barcode", "size"),
            haloo_count=("client", lambda values: (values == "Haloo").sum())
        )
    )

    hour_range = pd.date_range(
        start=first_hour,
        end=last_hour,
        freq="h",
        tz=NY_TIMEZONE
    )
    hourly_df = (
        pd.DataFrame({"hour": hour_range})
        .merge(hourly_df, on="hour", how="left")
        .fillna({
            "scan_count": 0,
            "haloo_count": 0,
        })
    )
    hourly_df["scan_count"] = hourly_df["scan_count"].astype(int)
    hourly_df["haloo_count"] = hourly_df["haloo_count"].astype(int)
    hourly_df["haloo_percentage"] = (
        hourly_df["haloo_count"] / hourly_df["scan_count"] * 100
    ).fillna(0)

    return hourly_df


def render_kpis(user_summary):
    total_count = int(user_summary["scan_count"].sum())
    active_people = len(user_summary)

    col1, col2 = st.columns(2)
    col1.metric("总生产数量", total_count)
    col2.metric("参与人数", active_people)


def render_client_kpis(client_summary):
    if client_summary.empty:
        return

    client_cols = st.columns(max(len(client_summary), 1))
    for index, row in client_summary.iterrows():
        client_cols[index].metric(
            row["client"],
            int(row["scan_count"])
        )


def build_user_client_pivot(user_client_summary):
    pivot_df = (
        user_client_summary
        .pivot_table(
            index="name",
            columns="client",
            values="scan_count",
            fill_value=0,
            aggfunc="sum"
        )
        .reset_index()
    )
    client_columns = [
        column
        for column in pivot_df.columns
        if column != "name"
    ]
    pivot_df["total"] = pivot_df[client_columns].sum(axis=1)
    if "Haloo" not in pivot_df.columns:
        pivot_df["Haloo"] = 0

    pivot_df["haloo_percentage"] = (
        pivot_df["Haloo"] / pivot_df["total"] * 100
    ).fillna(0)
    pivot_df = pivot_df.sort_values("total", ascending=False).reset_index(drop=True)

    return pivot_df, client_columns


def render_user_client_table(user_client_summary, title):
    st.subheader(f"{title}人员平台明细")

    pivot_df, _ = build_user_client_pivot(user_client_summary)
    summary_df = (
        pivot_df[
            [
                "name",
                "total",
                "Haloo",
                "haloo_percentage",
            ]
        ]
        .rename(columns={
            "name": "人员",
            "total": "总生产数量",
            "Haloo": "Haloo 数量",
            "haloo_percentage": "Haloo 占比",
        })
        .sort_values("Haloo 占比", ascending=False)
        .reset_index(drop=True)
    )
    summary_df["Haloo 占比"] = summary_df["Haloo 占比"].round(1)

    st.dataframe(
        summary_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Haloo 占比": st.column_config.ProgressColumn(
                "Haloo 占比",
                format="%.1f%%",
                min_value=0,
                max_value=100,
            )
        }
    )


def render_hourly_production(hourly_summary):
    if hourly_summary.empty:
        return

    st.subheader("每小时产量")

    chart_df = (
        hourly_summary
        .assign(小时=lambda data: data["hour"].dt.strftime("%H:00"))
        .set_index("小时")[["scan_count"]]
        .rename(columns={"scan_count": "产量"})
    )
    st.bar_chart(chart_df)

    table_df = (
        hourly_summary
        .assign(小时=lambda data: data["hour"].dt.strftime("%H:00"))
        [[
            "小时",
            "scan_count",
            "haloo_count",
            "haloo_percentage",
        ]]
        .rename(columns={
            "scan_count": "产量",
            "haloo_count": "Haloo 数量",
            "haloo_percentage": "Haloo 占比",
        })
    )
    table_df["Haloo 占比"] = table_df["Haloo 占比"].round(1)

    st.dataframe(
        table_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Haloo 占比": st.column_config.ProgressColumn(
                "Haloo 占比",
                format="%.1f%%",
                min_value=0,
                max_value=100,
            )
        }
    )


def render_production_summary(supabase, selected_date, title, user_column):
    st.title(title)

    try:
        raw_df = load_daily_production_rows(supabase, selected_date, user_column)
        if raw_df.empty:
            st.warning(f"{selected_date.isoformat()} 没有生产数据")
            st.stop()

        df = prepare_production_df(raw_df, user_column)

        if df.empty:
            st.warning(f"{selected_date.isoformat()} 没有{title}人员数据")
            st.stop()

        user_summary = summarize_by_user(df, user_column)
        client_summary = summarize_by_client(df)
        user_client_summary = summarize_by_user_and_client(df, user_column)
        hourly_summary = summarize_by_hour(df, selected_date)

        render_kpis(user_summary)
        render_client_kpis(client_summary)

        render_user_client_table(user_client_summary, title)
        render_hourly_production(hourly_summary)

    except Exception as e:
        st.error(
            f"数据加载失败：{e}"
        )
