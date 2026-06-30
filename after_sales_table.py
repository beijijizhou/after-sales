from db.supabase_client import supabase
import pandas as pd
import streamlit as st

def sales_table():
    st.title("售后数据")
    st.write("质检人员售后数据展示")
    response = supabase.rpc("get_after_sales_rate").execute()
    df = pd.DataFrame(response.data)

    st.dataframe(df)

    st.metric("总售后数量", df["after_sales_count"].sum())