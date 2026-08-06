from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from db.inventory.container.history import (
    build_container_history_display,
    load_container_events,
)
from db.inventory.container.workflow import (
    confirm_container_arrival_date,
    post_container_inventory,
)
from utils.auth import get_current_operator_name
from ui.inventory.container.reversal import render_container_undo_action


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


def render_status_update(
    supabase, raw_df, container_key, key_prefix="container_status",
):
    if not container_key or raw_df.empty:
        return
    target = raw_df[
        (raw_df["container_key"] == container_key)
        & (raw_df["status"].isin(["未到货", "延迟", "在途"]))
    ]
    if target.empty:
        return
    container_no = target["container_no"].dropna().astype(str).str.strip()
    label = container_no.iloc[0] if not container_no.empty else container_key
    st.subheader(f"确认到柜日期｜{label}")
    now = datetime.now(NY_TIMEZONE)
    expected = target["expected_arrival_date"].dropna()
    expected_date = (
        datetime.fromisoformat(str(expected.iloc[0])).date()
        if not expected.empty else now.date()
    )
    arrival_date = st.date_input(
        "确认到柜日期",
        value=expected_date,
        key=f"{key_prefix}_date_{container_key}",
    )
    note = st.text_input(
        "备注",
        key=f"{key_prefix}_note_{container_key}",
    )
    st.caption(
        "日期可以是明天或后天。点击后货柜进入“已到柜”，"
        "下一步确认入库；直接入库会自动同时记录当天到柜。"
    )
    arrival_col, post_col = st.columns(2)
    if arrival_col.button(
        "确认到柜", width="stretch",
        key=f"{key_prefix}_arrival_{container_key}",
    ):
        try:
            confirm_container_arrival_date(
                supabase,
                container_key,
                arrival_date,
                get_current_operator_name(),
                note,
            )
            st.success("到柜日期已确认，下一步可以确认入库")
            st.rerun()
        except Exception as error:
            st.error(f"到柜日期保存失败：{error}")

    total = int(target["quantity"].sum())
    if post_col.button(
        "到柜并直接入库",
        type="primary",
        width="stretch",
        key=f"{key_prefix}_direct_post_{container_key}",
    ):
        try:
            post_container_inventory(
                supabase,
                container_key,
                get_current_operator_name(),
                note,
            )
            st.success(f"入库成功：库存增加 {total:,} 件")
            st.rerun()
        except Exception as error:
            st.error(f"直接入库失败：{error}")


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
        st.info("请先在 Supabase SQL Editor 运行 sql/inventory/containers/inventory_container_history.sql")
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
            "实际到货时间（纽约）": st.column_config.TextColumn(
                "实际到货时间（纽约）"
            ),
            "确认时间（纽约）": st.column_config.TextColumn(
                "确认时间（纽约）"
            ),
            "备注": st.column_config.TextColumn("备注", width="large"),
        },
    )
    container_key = choices[selected]
    target = raw_df[raw_df["container_key"] == container_key]
    render_container_undo_action(
        supabase, target, container_key, "container_history"
    )
