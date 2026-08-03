from datetime import timedelta

import pandas as pd
import streamlit as st


WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
ALL_TIME = "全部时间"


def merge_current_week_with_overdue(current_df, overdue_df):
    frames = [frame for frame in (overdue_df, current_df) if not frame.empty]
    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)
    if "id" in result.columns:
        result = result.drop_duplicates("id", keep="last")
    return result.reset_index(drop=True)


def week_bounds(anchor_date):
    start = anchor_date - timedelta(days=anchor_date.weekday())
    return start, start + timedelta(days=6)


def render_week_selector(today, show_weekdays=True):
    current_start, _ = week_bounds(today)
    week_options = [
        current_start + timedelta(weeks=offset)
        for offset in range(27)
    ]
    options = [ALL_TIME, *week_options]
    if st.session_state.get("container_week_anchor") not in options:
        st.session_state["container_week_anchor"] = current_start
    selected = st.selectbox(
        "查看周",
        options,
        format_func=lambda value: (
            ALL_TIME if value == ALL_TIME
            else week_label(value, current_start, show_weekdays)
        ),
        key="container_week_anchor",
    )
    if selected == ALL_TIME:
        st.caption("全部时间：显示所有仍在途或未到货的货柜，包括延迟货柜。")
        return None, None
    start, end = selected_week_bounds(selected, today)
    range_label = (
        f"{start:%Y-%m-%d}（{WEEKDAYS[start.weekday()]}）至 "
        f"{end:%Y-%m-%d}（{WEEKDAYS[end.weekday()]}）"
        if show_weekdays
        else f"{start:%Y-%m-%d} 至 {end:%Y-%m-%d}"
    )
    st.caption(
        f"{'本周剩余时间' if selected == current_start else '所选周'}："
        f"{range_label}"
    )
    return start, end


def selected_week_bounds(selected_start, today):
    _, current_end = week_bounds(today)
    if selected_start <= today <= current_end:
        return today, current_end
    return selected_start, selected_start + timedelta(days=6)


def week_label(start, current_start, show_weekdays=True):
    end = start + timedelta(days=6)
    calendar = start.isocalendar()
    prefix = (
        "本周"
        if start == current_start
        else f"{calendar.year}年第{calendar.week}周"
    )
    if show_weekdays:
        return (
            f"{prefix}｜{start:%m/%d}（周一）- "
            f"{end:%m/%d}（周日）"
        )
    return f"{prefix}｜{start:%m/%d} - {end:%m/%d}"


def render_week_arrival_summary(
    raw_df,
    date_column,
    week_start,
    roll_overdue_to=None,
):
    data = raw_df.copy()
    if date_column not in data:
        data[date_column] = pd.NaT
    else:
        data[date_column] = pd.to_datetime(
            data[date_column], errors="coerce"
        ).dt.date
    data["_original_date"] = data[date_column]
    data["_schedule_date"] = data[date_column]
    if roll_overdue_to is not None:
        overdue = data["_schedule_date"] < week_start
        data.loc[overdue, "_schedule_date"] = roll_overdue_to
    columns = st.columns(7)
    for offset, column in enumerate(columns):
        day = week_start + timedelta(days=offset)
        rows = data[data["_schedule_date"] == day]
        container_count = (
            rows["container_key"].nunique()
            if "container_key" in rows else 0
        )
        quantity_values = (
            rows["quantity"]
            if "quantity" in rows else pd.Series(dtype=float)
        )
        quantity = int(pd.to_numeric(
            quantity_values, errors="coerce"
        ).fillna(0).sum())
        column.metric(
            f"{WEEKDAYS[offset]} {day:%m/%d}",
            f"{container_count} 柜",
            f"{quantity:,} 件",
            delta_color="off",
        )
        overdue_count = (
            rows.loc[
                rows["_original_date"] < week_start,
                "container_key",
            ].nunique()
            if "container_key" in rows else 0
        )
        if overdue_count:
            column.caption(f"含 {overdue_count} 柜逾期顺延")
