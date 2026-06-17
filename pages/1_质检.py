from datetime import datetime
from zoneinfo import ZoneInfo
from supabase import create_client
import streamlit as st
import supabase
import pandas as pd

from utils.utility import get_selected_date

url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
selected_date = get_selected_date()

supabase = create_client(url, key)

target_date = (
    datetime.now(
        ZoneInfo("America/New_York")
    )
    .date()
    .isoformat()
)
try:
    response = (
        supabase
        .rpc(
            "get_active_users_by_date",
            {
                "target_date": selected_date.isoformat()
            }
        )
        .execute()
    )

    df = pd.DataFrame(response.data)

    st.metric(
        "Total Scan Count",
        df["scan_count"].sum()
    )

    st.dataframe(df)

except Exception as e:
    st.error(
        f"Failed to load data: {e}"
    )

