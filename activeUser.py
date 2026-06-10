import streamlit as st

import supabase
response = (
    supabase
    .rpc(
        "get_active_users_by_date",
        {"target_date": "2026-06-08"}
    )
    .execute()
)

st.dataframe(response.data)