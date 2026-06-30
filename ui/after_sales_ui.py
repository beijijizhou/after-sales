import streamlit as st
import pandas as pd

from db.after_sale import save_after_sales_batch



def render_after_sales_section():
    st.divider()
    st.subheader("售后")

    df = st.session_state.get("search_df")

    if df is None:
        st.info("请先查询数据，再保存售后记录。")
        return

    reason = st.text_area("原因（选填）")

    if st.button("全部保存到售后"):

        save_after_sales_batch(df, reason=reason)

        st.success(f"已保存 {len(df)} 个条码")
