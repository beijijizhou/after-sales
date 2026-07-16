from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from db.inventory.container.history import (
    build_container_history_display,
    load_container_events,
    update_container_status,
)
from utils.auth import get_current_operator_name


NY_TIMEZONE = ZoneInfo("America/New_York")


def build_container_choices(raw_df, allowed_statuses=None):
    if raw_df.empty:
        return {}, []
    columns = [
        "container_key", "container_no", "status", "expected_arrival_date",
        "actual_arrival_date",
    ]
    unique = raw_df[columns].drop_duplicates("container_key").copy()
    if allowed_statuses:
        unique = unique[unique["status"].isin(allowed_statuses)]
    choices = {}
    for row in unique.to_dict("records"):
        number = row.get("container_no") or row["container_key"]
        label = str(number)
        choices[label] = row["container_key"]
    labels = sorted(choices)
    return choices, labels


def render_status_update(supabase, raw_df, container_key):
    if not container_key or raw_df.empty:
        return
    target = raw_df[
        (raw_df["container_key"] == container_key)
        & (raw_df["status"].isin(["未到货", "延迟"]))
    ]
    if target.empty:
        return
    container_no = target["container_no"].dropna().astype(str).str.strip()
    label = container_no.iloc[0] if not container_no.empty else container_key
    st.subheader(f"确认到货｜{label}")
    effective_date = st.date_input(
        "实际到货日期",
        value=datetime.now(NY_TIMEZONE).date(),
        key="container_status_date",
    )
    note = st.text_input("备注", key="container_status_note")
    if not st.button("确认已到货", width="stretch"):
        return
    try:
        update_container_status(
            supabase,
            container_key,
            "已到货",
            effective_date,
            get_current_operator_name(),
            note,
        )
        st.success("货柜已确认到货，并已写入到货历史")
        st.rerun()
    except Exception as error:
        st.error(f"货柜状态保存失败：{error}")
        st.info("请先在 Supabase SQL Editor 运行 sql/inventory_container_history.sql")


def render_container_history(supabase, raw_df):
    st.subheader("操作记录")
    choices, labels = build_container_choices(raw_df)
    if not labels:
        st.info("当前范围内没有货柜历史")
        return
    selected = st.selectbox("查看货柜", labels, key="container_history_target")
    try:
        events_df = load_container_events(supabase, choices[selected])
        display_df = build_container_history_display(events_df)
    except Exception as error:
        st.error(f"货柜历史加载失败：{error}")
        st.info("请先在 Supabase SQL Editor 运行 sql/inventory_container_history.sql")
        return
    if display_df.empty:
        st.info("这个货柜还没有历史记录")
        return
    st.dataframe(
        display_df,
        hide_index=True,
        width="stretch",
        column_config={
            "事件日期": st.column_config.DateColumn("事件日期"),
            "备注": st.column_config.TextColumn("备注", width="large"),
        },
    )
