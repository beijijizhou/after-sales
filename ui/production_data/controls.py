from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st


def render_production_filters(platform):
    today = datetime.now(ZoneInfo("America/New_York")).date()
    period = st.segmented_control(
        "快捷范围",
        ["当天", "近7日", "近14日", "近28日", "自定义"],
        default="当天",
    )
    if period == "自定义":
        date_columns = st.columns(2)
        start_date = date_columns[0].date_input(
            "开始日期",
            value=today,
            max_value=today,
            key="production_custom_start_date",
        )
        end_key = "production_custom_end_date"
        if (
            end_key in st.session_state
            and st.session_state[end_key] < start_date
        ):
            st.session_state[end_key] = start_date
        end_date = date_columns[1].date_input(
            "结束日期",
            value=today,
            min_value=start_date,
            max_value=today,
            key=end_key,
        )
    else:
        selected_date = st.date_input(
            "生产日期" if period == "当天" else "截止日期",
            value=today,
            max_value=today,
            key=f"production_end_date_{period}",
        )
        start_date, end_date = resolve_production_period(
            period, selected_date
        )
        if period != "当天":
            st.caption(
                f"查询区间：{start_date:%Y/%m/%d} – {end_date:%Y/%m/%d}"
            )
    selected_range = (start_date, end_date)
    start_col, end_col = st.columns(2)
    with start_col:
        start_hour = st.selectbox(
            "开始小时（纽约时间）",
            range(24),
            index=0,
            format_func=_format_hour,
        )
    with end_col:
        end_hour = st.selectbox(
            "结束小时（纽约时间）",
            range(24),
            index=23,
            format_func=_format_end_hour,
        )
    st.caption("小时筛选适用于全部平台；结束小时包含该小时全部数据。")
    force_refresh = st.checkbox(
        "强制重新获取（忽略本地缓存）",
        value=False,
        help="未勾选时，相同平台和时间范围会直接读取本地缓存。",
    )

    valid_dates = start_date <= end_date
    valid_hours = (
        not valid_dates
        or start_date != end_date
        or start_hour <= end_hour
    )
    submitted = st.button(
        "获取生产数据",
        type="primary",
        width="stretch",
        disabled=not valid_dates or not platform or not valid_hours,
    )
    if not valid_hours:
        st.warning("同一天查询时，结束小时不能早于开始小时。")
    return selected_range, start_hour, end_hour, force_refresh, submitted


def resolve_production_period(period, selected_date):
    days = {
        "当天": 1,
        "近7日": 7,
        "近14日": 14,
        "近28日": 28,
    }.get(period, 1)
    end_date = selected_date
    if isinstance(end_date, datetime):
        end_date = end_date.date()
    if not isinstance(end_date, date):
        raise ValueError("生产日期无效")
    return end_date - timedelta(days=days - 1), end_date


def _format_hour(value):
    return f"{value:02d}:00"


def _format_end_hour(value):
    return f"{value:02d}:59"
