from supabase import create_client
import streamlit as st

import pandas as pd

from after_sales_table import sales_table
from ui.after_sales_ui import render_after_sales_section

url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]

supabase = create_client(url, key)

st.title("批量生产订单/条码售后数据查询")

input_text = st.text_area(
    "Paste PO / Barcode list (one per line)",
    height=200
)

col1, col2 = st.columns(2)

exact_search = col1.button("精准匹配")
like_search = col2.button("模糊匹配")

if exact_search or like_search:

    barcodes = list({
        x.strip()
        for x in input_text.split("\n")
        if x.strip()
    })

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
                .select("barcode,scanned_by,scanned_at")
                .in_("barcode", barcodes)
                .execute()
            )

            results = response.data

            found_inputs = {
                row["barcode"]
                for row in response.data
            }

        else:

            for barcode in barcodes:

                response = (
                    supabase
                    .table("barcode_scans")
                    .select("barcode,scanned_by,scanned_at")
                    .ilike("barcode", f"%{barcode}%")
                    .limit(20)
                    .execute()
                )

                if response.data:
                    found_inputs.add(barcode)
                    results.extend(response.data)

    if results:

        df = pd.DataFrame(results)
        st.session_state["search_df"] = df
        # remove duplicate rows
        df = df.drop_duplicates()

        st.success(f"Found {len(df)} records")

        st.dataframe(
            df,
            use_container_width=True
        )

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

        st.text_area(
            "Missing Barcodes",
            "\n".join(barcodes),
            height=200
        )


render_after_sales_section()

sales_table()
