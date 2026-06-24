import streamlit as st
from supabase import create_client
import pandas as pd

url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]

supabase = create_client(url, key)

st.title("Batch Barcode Search")

input_text = st.text_area(
    "Paste PO / Barcode list (one per line)",
    height=200
)

col1, col2 = st.columns(2)

exact_search = col1.button("精准匹配")
like_search = col2.button("模糊匹配")

if exact_search or like_search:

    barcodes = [
        x.strip()
        for x in input_text.split("\n")
        if x.strip()
    ]

    if not barcodes:
        st.warning("No input found")
        st.stop()

    results = []
    found_inputs = set()

    with st.spinner("Searching..."):

        if exact_search:
            response = (
                supabase
                .table("barcode_scans")
                .select("*")
                .in_("barcode", barcodes)
                .execute()
            )

            results = response.data

            found_inputs = {
                row["barcode"]
                for row in response.data
            }

        else:  # Like Match

            for barcode in barcodes:
                response = (
                    supabase
                    .table("barcode_scans")
                    .select("*")
                    .ilike("barcode", f"%{barcode}%")
                    .execute()
                )

                if response.data:
                    found_inputs.add(barcode)
                    results.extend(response.data)

    if results:

        st.success(f"Found {len(results)} records")

        df = pd.DataFrame(results)

        st.dataframe(df)

        if exact_search:
            missing_barcodes = [
                barcode
                for barcode in barcodes
                if barcode not in found_inputs
            ]
        else:
            missing_barcodes = [
                barcode
                for barcode in barcodes
                if barcode not in found_inputs
            ]

        if missing_barcodes:
            st.warning(
                f"{len(missing_barcodes)} barcode(s) not found"
            )

            st.text_area(
                "Missing Barcodes",
                "\n".join(missing_barcodes),
                height=200
            )

    else:
        st.warning("No matching records found")