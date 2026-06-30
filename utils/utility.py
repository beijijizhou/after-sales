from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st


def get_selected_date():
    return st.date_input(
        "选择日期",
        value=datetime.now(
            ZoneInfo("America/New_York")
        ).date(),
        max_value=datetime.now(
            ZoneInfo("America/New_York")
        ).date()
    )
