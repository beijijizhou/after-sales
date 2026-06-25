import streamlit as st
import pandas as pd

from db.after_sale import save_after_sales_batch



def render_after_sales_section():
    st.divider()
    st.subheader("After Sales")

    df = st.session_state.get("search_df")

    if df is None:
        st.info("Run a search first before saving after sales data.")
        return

    reason = st.text_area("Reason (optional)")

    if st.button("Save All To After Sales"):

        save_after_sales_batch(df, reason=reason)

        st.success(f"Saved {len(df)} barcodes")