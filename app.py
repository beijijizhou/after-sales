import streamlit as st
from supabase import create_client
import os


url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]

supabase = create_client(url, key)

st.title("Batch Barcode Search")

input_text = st.text_area(
    "Paste PO / Barcode list (one per line)",
    height=200
)

if st.button("Search"):
    # split by newline and clean empty lines
    barcodes = [
        x.strip()
        for x in input_text.split("\n")
        if x.strip()
    ]

    if not barcodes:
        st.warning("No input found")
        st.stop()

    response = (
        supabase
        .table("barcode_scans")
        .select("*")
        .in_("barcode", barcodes)
        .execute()
    )

    if response.data:
        st.success(f"Found {len(response.data)} records")
        st.dataframe(response.data)
    else:
        st.warning("No matching records found")

response = (
    supabase
    .rpc(
        "get_active_users_by_date",
        {"target_date": "2026-06-08"}
    )
    .execute()
)

st.dataframe(response.data)
