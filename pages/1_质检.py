from datetime import datetime
from zoneinfo import ZoneInfo
from supabase import create_client
import streamlit as st
import supabase
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]

supabase = create_client(url, key)

target_date = (
    datetime.now(
        ZoneInfo("America/New_York")
    )
    .date()
    .isoformat()
)
response = (
    supabase
    .rpc(
        "get_active_users_by_date",
        {"target_date": target_date}
    )
    .execute()
)

st.dataframe(response.data)