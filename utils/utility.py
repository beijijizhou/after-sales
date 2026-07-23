from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st

from utils.date_display import format_date_with_weekday


def get_selected_date():
    selected_date = st.date_input(
        "选择日期",
        value=datetime.now(
            ZoneInfo("America/New_York")
        ).date(),
        max_value=datetime.now(
            ZoneInfo("America/New_York")
        ).date()
    )

    st.caption(f"已选择：{format_date_with_weekday(selected_date)}")

    return selected_date
