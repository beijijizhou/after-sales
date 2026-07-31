import pandas as pd
import streamlit as st

from db.inventory.container.history import (
    build_container_history_display,
    load_container_events,
)
from db.inventory.container.repository import load_container_search_records
from db.inventory.container.tables import build_container_display
from ui.inventory.container.tables import render_container_detail
from utils.auth import has_permission


def build_container_search_choices(raw_df):
    if raw_df.empty:
        return {}
    choices = {}
    for key, rows in raw_df.groupby("container_key", sort=False):
        row = rows.iloc[0].to_dict()
        key = row["container_key"]
        number = row.get("container_no") or key
        status = row.get("status") or "状态未知"
        actual = row.get("actual_arrival_date")
        expected = row.get("expected_arrival_date")
        if _has_value(actual):
            date_text = f"｜到柜 {actual}"
        elif _has_value(expected):
            date_text = f"｜预计 {expected}"
        else:
            date_text = ""
        department = str(row.get("department") or "").strip()
        category = str(row.get("category") or "").strip()
        business = " · ".join(value for value in [department, category] if value)
        business_text = f"｜{business}" if business else ""
        total = int(pd.to_numeric(rows["quantity"], errors="coerce").fillna(0).sum())
        choices[key] = (
            f"{number}｜{status}{date_text}{business_text}｜{total:,} 件"
        )
    return choices


def render_container_search(supabase):
    try:
        raw_df = load_container_search_records(supabase)
    except Exception as error:
        st.error(f"货柜列表加载失败：{error}")
        return
    if raw_df.empty:
        st.info("目前还没有货柜记录")
        return
    choices = build_container_search_choices(raw_df)
    st.caption("可以直接浏览，也可以输入货柜号、部门或品类关键词查找。")
    container_key = st.selectbox(
        "查找货柜",
        ["", *choices],
        format_func=lambda value: (
            "请选择货柜" if not value else choices[value]
        ),
        key="container_search_dropdown",
    )
    if not container_key:
        return
    target = raw_df[raw_df["container_key"] == container_key]
    render_container_detail(
        build_container_display(
            target, include_cost=has_permission("can_view_cost")
        ),
        container_key,
    )
    _render_search_history(supabase, container_key)


def _has_value(value):
    return value is not None and not pd.isna(value) and str(value).strip()


def _render_search_history(supabase, container_key):
    events = load_container_events(supabase, container_key)
    history = build_container_history_display(events)
    st.subheader("操作记录")
    if history.empty:
        st.info("这个货柜还没有操作记录")
        return
    st.dataframe(
        history,
        hide_index=True,
        width="stretch",
        column_config={
            "事件日期": st.column_config.DateColumn("事件日期"),
            "备注": st.column_config.TextColumn("备注", width="large"),
        },
    )
