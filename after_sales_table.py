from zoneinfo import ZoneInfo

import altair as alt
from db.supabase_client import supabase
from db.after_sale import (
    load_after_sales_detail_by_person,
    load_after_sales_people_summary,
)
import pandas as pd
import streamlit as st

NY_TIMEZONE = ZoneInfo("America/New_York")


def sales_table():
    st.title("售后数据")
    st.write("质检人员售后数据展示")
    response = supabase.rpc("get_after_sales_rate").execute()
    df = pd.DataFrame(response.data)

    st.dataframe(df)

    st.metric("总售后数量", df["after_sales_count"].sum())
    render_after_sales_shipping_chart()
    render_person_after_sales_detail()


def render_after_sales_shipping_chart():
    summary_df = pd.DataFrame(load_after_sales_people_summary())
    if summary_df.empty:
        return

    latest_input = get_latest_input_time(summary_df)
    if latest_input:
        st.metric("表格最后更新时间", latest_input)

    chart_df = build_shipping_chart_df(summary_df)
    if chart_df.empty:
        return

    st.subheader("售后发货日期统计")
    chart = (
        alt.Chart(chart_df)
        .mark_bar(color="#2563EB")
        .encode(
            x=alt.X("发货日期:T", title="发货日期"),
            y=alt.Y("发货件数:Q", title="发货件数"),
            tooltip=[
                alt.Tooltip("发货日期:T", title="发货日期"),
                alt.Tooltip("发货件数:Q", title="发货件数"),
            ],
        )
        .properties(height=320)
    )
    st.altair_chart(chart, use_container_width=True)


def get_latest_input_time(df):
    if "entered_at" not in df.columns:
        return ""

    entered_at = pd.to_datetime(df["entered_at"], errors="coerce", utc=True).dropna()
    if entered_at.empty:
        return ""

    latest_at = entered_at.max().tz_convert(NY_TIMEZONE)
    return latest_at.strftime("%Y-%m-%d %H:%M:%S")


def build_shipping_chart_df(df):
    if "scanned_at" not in df.columns:
        return pd.DataFrame()

    chart_df = df.copy()
    chart_df["发货日期"] = to_datetime_series(chart_df, "scanned_at").dt.tz_convert(NY_TIMEZONE).dt.date
    chart_df["quantity"] = pd.to_numeric(chart_df.get("quantity", 1), errors="coerce").fillna(1)
    chart_df = chart_df.dropna(subset=["发货日期"])
    if chart_df.empty:
        return pd.DataFrame()

    return (
        chart_df
        .groupby("发货日期", as_index=False)["quantity"]
        .sum()
        .rename(columns={"quantity": "发货件数"})
        .sort_values("发货日期")
    )


def render_person_after_sales_detail():
    st.subheader("个人售后明细")
    summary_df = build_people_summary_df()
    if summary_df.empty:
        st.info("暂无售后明细")
        return

    person_options = summary_df["质检人员"].tolist()
    selected_person = st.selectbox(
        "筛选质检人员",
        options=["", *person_options],
        format_func=lambda value: "请选择质检人员" if value == "" else value,
    )
    if not selected_person:
        st.dataframe(summary_df, hide_index=True, use_container_width=True)
        return

    detail_df = build_person_detail_df(selected_person)
    if detail_df.empty:
        st.warning("未找到该人员售后明细")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("售后条码数", len(detail_df))
    col2.metric("售后件数", int(detail_df["件数"].sum()))
    col3.metric("总金额", f"{detail_df['总金额'].sum():.2f}")

    st.dataframe(
        detail_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "件数": st.column_config.NumberColumn("件数", format="%d"),
            "总金额": st.column_config.NumberColumn("总金额", format="%.2f"),
        },
    )


def build_people_summary_df():
    df = pd.DataFrame(load_after_sales_people_summary())
    if df.empty or "scanned_by" not in df.columns:
        return pd.DataFrame()

    df["amount"] = pd.to_numeric(df.get("amount", 0), errors="coerce").fillna(0)
    df["quantity"] = pd.to_numeric(df.get("quantity", 1), errors="coerce").fillna(1)
    df["entered_at_ny"] = to_datetime_series(df, "entered_at")
    summary_df = (
        df
        .groupby("scanned_by", as_index=False)
        .agg(
            after_sales_count=("scanned_by", "size"),
            quantity=("quantity", "sum"),
            amount=("amount", "sum"),
            entered_at_ny=("entered_at_ny", "max"),
        )
        .rename(columns={
            "scanned_by": "质检人员",
            "after_sales_count": "售后条码数",
            "quantity": "售后件数",
            "amount": "总金额",
            "entered_at_ny": "最后输入时间",
        })
        .sort_values("售后条码数", ascending=False)
        .reset_index(drop=True)
    )
    summary_df["最后输入时间"] = summary_df["最后输入时间"].apply(format_ny_datetime)
    return summary_df


def build_person_detail_df(person):
    df = pd.DataFrame(load_after_sales_detail_by_person(person))
    if df.empty:
        return pd.DataFrame()

    df["amount"] = pd.to_numeric(df.get("amount", 0), errors="coerce").fillna(0)
    df["quantity"] = pd.to_numeric(df.get("quantity", 1), errors="coerce").fillna(1).astype(int)
    df["entered_at"] = to_datetime_series(df, "entered_at").apply(format_ny_datetime)
    df["scanned_at"] = to_datetime_series(df, "scanned_at").apply(format_ny_datetime)
    return df.rename(columns={
        "barcode": "条码",
        "scanned_by": "质检人员",
        "product_type": "售后类型",
        "quantity": "件数",
        "amount": "总金额",
        "reason": "售后原因",
        "scanned_at": "发货时间",
        "entered_at": "输入时间",
    })[["条码", "质检人员", "售后类型", "件数", "发货时间", "输入时间", "总金额", "售后原因"]]


def format_ny_datetime(value):
    if pd.isna(value):
        return ""
    return value.tz_convert(NY_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


def to_datetime_series(df, column):
    if column not in df.columns:
        return pd.Series(pd.NaT, index=df.index)
    return pd.to_datetime(df[column], errors="coerce", utc=True)
