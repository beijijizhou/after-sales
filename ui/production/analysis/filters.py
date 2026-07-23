from dataclasses import dataclass
from datetime import date

import streamlit as st

from utils.production.constants import HALOO_PLATFORM, OTHER_CLIENT
from utils.production.period_summary import filter_period_rows


@dataclass(frozen=True)
class PeriodFilterState:
    start_date: date
    end_date: date
    people: tuple[str, ...]
    client_type: str
    platforms: tuple[str, ...]


def render_period_date_filter(default_start, default_end):
    selected_dates = st.date_input(
        "日期范围",
        value=(default_start, default_end),
        max_value=default_end,
        key="qa_period_dates_v2",
    )
    return normalize_date_range(
        selected_dates, default_start, default_end
    )


def render_period_filters(rows, start_date, end_date):
    person_col, client_col, platform_col = st.columns(3)
    people_options = sorted(rows["人员"].dropna().unique())
    reset_invalid_selection("qa_period_people", people_options)
    people = person_col.multiselect(
        "质检人员", people_options,
        key="qa_period_people", placeholder="全部人员",
    )

    people_rows = filter_period_rows(
        rows, start_date, end_date, people=people
    )
    client_type = client_col.segmented_control(
        "客户类型",
        ["全部", HALOO_PLATFORM, OTHER_CLIENT],
        default="全部",
        key="qa_period_client_type",
    ) or "全部"

    client_rows = filter_period_rows(
        people_rows, start_date, end_date,
        client_type=client_type,
    )
    platform_options = sorted(client_rows["平台"].dropna().unique())
    reset_invalid_selection("qa_period_platforms", platform_options)
    platforms = platform_col.multiselect(
        "具体平台", platform_options,
        key="qa_period_platforms", placeholder="全部平台",
    )

    filtered = filter_period_rows(
        rows, start_date, end_date, people,
        client_type, platforms,
    )
    state = PeriodFilterState(
        start_date=start_date,
        end_date=end_date,
        people=tuple(people),
        client_type=client_type,
        platforms=tuple(platforms),
    )
    return filtered, state


def normalize_date_range(value, default_start, default_end):
    if isinstance(value, (tuple, list)):
        if len(value) == 2:
            return min(value), max(value)
        if len(value) == 1:
            return value[0], value[0]
    return default_start, default_end


def reset_invalid_selection(key, options):
    if key not in st.session_state:
        return
    st.session_state[key] = [
        value for value in st.session_state[key] if value in options
    ]
