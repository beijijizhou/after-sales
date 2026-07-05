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


def load_daily_production_rows(supabase, selected_date):
    start_at, end_at = get_date_range(selected_date)
    rows = []
    page_size = 1000
    offset = 0

    while True:
        response = (
            supabase
            .table("barcode_scans")
            .select("barcode,scanned_by,hotstamp_by,scanned_at")
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


def get_platform(barcode):
    barcode = str(barcode).strip().upper()

    if barcode.startswith("SCGD-"):
        return "Hum Bird"

    if len(barcode.split("-")[0]) == 6:
        return "S2B"

    return "其他"


def prepare_production_df(df, user_column):
    if df.empty or user_column not in df.columns:
        return pd.DataFrame()

    df = (
        df
        .dropna(subset=[user_column])
        .assign(**{
            user_column: lambda data: data[user_column].astype(str).str.strip(),
            "platform": lambda data: data["barcode"].apply(get_platform),
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


def summarize_by_platform(df):
    return (
        df
        .groupby("platform", as_index=False)
        .size()
        .rename(columns={"size": "scan_count"})
        .sort_values("scan_count", ascending=False)
        .reset_index(drop=True)
    )


def summarize_by_user_and_platform(df, user_column):
    return (
        df
        .groupby([user_column, "platform"], as_index=False)
        .size()
        .rename(columns={
            user_column: "name",
            "size": "scan_count",
        })
        .sort_values(["name", "scan_count"], ascending=[True, False])
        .reset_index(drop=True)
    )


def get_top_name(user_summary):
    if user_summary.empty:
        return "-"

    return user_summary.iloc[0]["name"]


def render_kpis(user_summary):
    total_count = int(user_summary["scan_count"].sum())
    active_people = len(user_summary)
    top_name = get_top_name(user_summary)

    col1, col2, col3 = st.columns(3)
    col1.metric("总生产数量", total_count)
    col2.metric("参与人数", active_people)
    col3.metric("最高产出人员", top_name)


def render_platform_kpis(platform_summary):
    if platform_summary.empty:
        return

    platform_cols = st.columns(max(len(platform_summary), 1))
    for index, row in platform_summary.iterrows():
        platform_cols[index].metric(
            row["platform"],
            int(row["scan_count"])
        )


def render_people_ranking(user_summary):
    st.subheader("人员产出排行")

    max_count = int(user_summary["scan_count"].max())
    for _, row in user_summary.head(10).iterrows():
        count = int(row["scan_count"])
        ratio = count / max_count if max_count else 0

        left, right = st.columns([3, 1])
        left.write(row["name"])
        right.write(count)
        st.progress(ratio)


def build_user_platform_pivot(user_platform_summary):
    pivot_df = (
        user_platform_summary
        .pivot_table(
            index="name",
            columns="platform",
            values="scan_count",
            fill_value=0,
            aggfunc="sum"
        )
        .reset_index()
    )
    platform_columns = [
        column
        for column in pivot_df.columns
        if column != "name"
    ]
    pivot_df["total"] = pivot_df[platform_columns].sum(axis=1)
    if "Hum Bird" not in pivot_df.columns:
        pivot_df["Hum Bird"] = 0

    pivot_df["hum_bird_percentage"] = (
        pivot_df["Hum Bird"] / pivot_df["total"] * 100
    ).fillna(0)
    pivot_df["non_hum_bird_count"] = pivot_df["total"] - pivot_df["Hum Bird"]
    pivot_df = pivot_df.sort_values("total", ascending=False).reset_index(drop=True)

    return pivot_df, platform_columns


def render_hum_bird_ratio_ranking(user_platform_summary):
    st.subheader("个人 Hum Bird 占比")

    pivot_df, _ = build_user_platform_pivot(user_platform_summary)
    ranking_df = pivot_df.sort_values(
        ["hum_bird_percentage", "total"],
        ascending=[False, False]
    )

    for _, row in ranking_df.iterrows():
        left, middle, right = st.columns([3, 2, 2])
        percentage = float(row["hum_bird_percentage"])

        left.write(row["name"])
        middle.progress(percentage / 100)
        right.write(
            f"{percentage:.1f}% | 非 Hum Bird: {int(row['non_hum_bird_count'])}"
        )


def render_user_platform_cards(user_platform_summary):
    st.subheader("人员平台明细")

    pivot_df, platform_columns = build_user_platform_pivot(user_platform_summary)

    for start in range(0, len(pivot_df), 3):
        columns = st.columns(3)
        for column, (_, row) in zip(columns, pivot_df.iloc[start:start + 3].iterrows()):
            column.metric(row["name"], int(row["total"]))
            column.caption(
                f"Hum Bird 占比: {float(row['hum_bird_percentage']):.1f}% | "
                f"非 Hum Bird: {int(row['non_hum_bird_count'])}"
            )
            parts = [
                f"{platform}: {int(row[platform])}"
                for platform in platform_columns
                if int(row[platform]) > 0
            ]
            column.caption(" / ".join(parts))


def render_detail_table(df, user_column):
    detail_columns = [
        "barcode",
        user_column,
        "platform",
        "scanned_at",
    ]

    with st.expander("查看生产明细"):
        st.dataframe(
            df[detail_columns].sort_values("scanned_at", ascending=False),
            use_container_width=True
        )


def render_production_summary(supabase, selected_date, title, user_column):
    st.title(title)

    try:
        raw_df = load_daily_production_rows(supabase, selected_date)
        df = prepare_production_df(raw_df, user_column)

        if df.empty:
            st.warning("未找到数据")
            st.stop()

        user_summary = summarize_by_user(df, user_column)
        platform_summary = summarize_by_platform(df)
        user_platform_summary = summarize_by_user_and_platform(df, user_column)

        render_kpis(user_summary)
        render_platform_kpis(platform_summary)

        render_people_ranking(user_summary)
        render_hum_bird_ratio_ranking(user_platform_summary)
        render_user_platform_cards(user_platform_summary)
        render_detail_table(df, user_column)

    except Exception as e:
        st.error(
            f"数据加载失败：{e}"
        )
