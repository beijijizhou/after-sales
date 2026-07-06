from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st

WEEKDAY_NAMES = [
    "星期一",
    "星期二",
    "星期三",
    "星期四",
    "星期五",
    "星期六",
    "星期日",
]


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

    st.caption(f"已选择：{selected_date.isoformat()} {WEEKDAY_NAMES[selected_date.weekday()]}")

    return selected_date
