from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st


def get_date_range(selected_date):
    start_at = datetime.combine(
        selected_date,
        time.min,
        tzinfo=ZoneInfo("America/New_York")
    ).isoformat()
    end_at = datetime.combine(
        selected_date,
        time.max,
        tzinfo=ZoneInfo("America/New_York")
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
            .select(f"barcode,{user_column}")
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


def get_client(barcode):
    barcode = str(barcode).strip().upper()
    order_id = barcode

    if barcode.startswith("SCGD-"):
        order_id = barcode.removeprefix("SCGD-").rsplit("-", 1)[0]

    if "-" in order_id:
        order_id = order_id.rsplit("-", 1)[0]

    if len(order_id) == 7 and order_id.startswith("B"):
        return "Haloo"

    return "小平台"


def prepare_production_df(df, user_column):
    if df.empty or user_column not in df.columns:
        return pd.DataFrame()

    df = (
        df
        .dropna(subset=[user_column])
        .assign(**{
            user_column: lambda data: data[user_column].astype(str).str.strip(),
            "client": lambda data: data["barcode"].apply(get_client),
        })
    )
    df = df[df[user_column] != ""]

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


def render_user_client_table(user_client_summary):
    st.subheader("质检人员平台明细")

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

        render_kpis(user_summary)
        render_client_kpis(client_summary)

        render_user_client_table(user_client_summary)

    except Exception as e:
        st.error(
            f"数据加载失败：{e}"
        )
