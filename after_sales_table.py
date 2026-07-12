from db.supabase_client import supabase
from db.after_sale import (
    load_after_sales_detail_by_person,
    load_after_sales_people_summary,
)
import pandas as pd
import streamlit as st


def sales_table():
    st.title("售后数据")
    st.write("质检人员售后数据展示")
    response = supabase.rpc("get_after_sales_rate").execute()
    df = pd.DataFrame(response.data)

    st.dataframe(df)

    st.metric("总售后数量", df["after_sales_count"].sum())
    render_person_after_sales_detail()


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
    summary_df = (
        df
        .groupby("scanned_by", as_index=False)
        .agg(
            after_sales_count=("scanned_by", "size"),
            quantity=("quantity", "sum"),
            amount=("amount", "sum"),
        )
        .rename(columns={
            "scanned_by": "质检人员",
            "after_sales_count": "售后条码数",
            "quantity": "售后件数",
            "amount": "总金额",
        })
        .sort_values("售后条码数", ascending=False)
        .reset_index(drop=True)
    )
    return summary_df


def build_person_detail_df(person):
    df = pd.DataFrame(load_after_sales_detail_by_person(person))
    if df.empty:
        return pd.DataFrame()

    df["amount"] = pd.to_numeric(df.get("amount", 0), errors="coerce").fillna(0)
    df["quantity"] = pd.to_numeric(df.get("quantity", 1), errors="coerce").fillna(1).astype(int)
    return df.rename(columns={
        "barcode": "条码",
        "scanned_by": "质检人员",
        "product_type": "售后类型",
        "quantity": "件数",
        "amount": "总金额",
        "reason": "售后原因",
    })[["条码", "质检人员", "售后类型", "件数", "总金额", "售后原因"]]
