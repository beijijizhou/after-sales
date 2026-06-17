
import streamlit as st
from supabase import create_client



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
    with st.spinner("Searching barcodes..."):
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
    
        found_barcodes = {
            row["barcode"]
            for row in response.data
        }
    
        missing_barcodes = [
            barcode
            for barcode in barcodes
            if barcode not in found_barcodes
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

