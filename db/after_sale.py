import streamlit as st
from supabase import create_client

# create client once
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]

supabase = create_client(url, key)


def save_after_sales(barcode: str, scanned_by: str):
    return (
        supabase
        .table("after_sales")
        .upsert({
            "barcode": barcode,
            "scanned_by": scanned_by,
        })
        .execute()
    )


def save_after_sales_batch(df, reason=""):
    records = [
        {
            "barcode": row["barcode"],
            "scanned_by": row["scanned_by"],
            "reason": reason
        }
        for _, row in df.iterrows()
    ]

    return (
        supabase
        .table("after_sales")
        .upsert(records)
        .execute()
    )