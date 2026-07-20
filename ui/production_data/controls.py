from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st


def render_production_filters(platform):
    today = datetime.now(ZoneInfo("America/New_York")).date()
    period = st.segmented_control(
        "快捷范围",
        ["当天", "近7日", "近14日", "近28日", "自定义"],
        default="当天",
    )
    period_days = {
        "当天": 1,
        "近7日": 7,
        "近14日": 14,
        "近28日": 28,
        "自定义": 1,
    }
    start_date = today - timedelta(days=period_days[period] - 1)
    selected_range = st.date_input(
        "生产日期",
        value=(start_date, today),
        max_value=today,
        key=f"production_date_range_{period}",
    )
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

    has_date_range = len(selected_range) == 2
    valid_hours = (
        not has_date_range
        or selected_range[0] != selected_range[1]
        or start_hour <= end_hour
    )
    submitted = st.button(
        "获取生产数据",
        type="primary",
        width="stretch",
        disabled=not has_date_range or not platform or not valid_hours,
    )
    if not has_date_range:
        st.info("请选择开始日期和结束日期。")
    elif not valid_hours:
        st.warning("同一天查询时，结束小时不能早于开始小时。")
    return selected_range, start_hour, end_hour, force_refresh, submitted


def _format_hour(value):
    return f"{value:02d}:00"


def _format_end_hour(value):
    return f"{value:02d}:59"
