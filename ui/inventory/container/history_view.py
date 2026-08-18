from datetime import timedelta

import pandas as pd
import streamlit as st

from db.inventory.container.repository import load_inventory_containers
from db.inventory.container.history import (
    attach_arrival_confirmation_times,
    load_container_events,
)
from db.inventory.container.tables import (
    build_arrival_batch_summary,
    build_container_display,
    sort_arrival_history_rows,
)
from ui.inventory.container.selection import (
    container_selection_widget_key,
    selected_container_key,
)
from ui.inventory.container.tables import (
    render_container_detail,
    render_container_inventory_summary,
)
from ui.table_layout import fit_table_height
from utils.auth import has_permission


def render_arrival_history_table(
    supabase, start_date, end_date, department, category,
    brands, materials, colors, sizes,
):
    st.subheader("到柜记录")
    try:
        raw_df = load_inventory_containers(
            supabase, start_date, end_date, department, category,
            statuses=["已到柜", "已入库", "已到货"],
            date_field="actual_arrival_date",
            brands=brands, materials=materials, colors=colors, sizes=sizes,
        )
    except Exception as error:
        st.error(f"到柜历史加载失败：{error}")
        return pd.DataFrame(), None
    if raw_df.empty:
        st.info("当前日期范围内没有到柜记录")
        return raw_df, None
    try:
        raw_df = attach_arrival_confirmation_times(
            raw_df, load_container_events(supabase)
        )
    except Exception as error:
        st.warning(f"确认到柜时间加载失败，暂按实际到货时间排序：{error}")
    quantities = pd.to_numeric(
        raw_df["quantity"], errors="coerce"
    ).fillna(0)
    col1, col2 = st.columns(2)
    col1.metric("到柜总件数", int(quantities.sum()))
    col2.metric("到柜数量", raw_df["container_key"].nunique())
    render_container_inventory_summary(
        raw_df, "到柜库存汇总"
    )
    st.subheader("到柜批次")
    st.caption("每个货柜只显示一行；点选批次后查看该柜的完整 SKU 明细和操作记录。")
    sort_label = st.segmented_control(
        "记录排序",
        ["按到柜时间", "按部门"],
        default="按到柜时间",
        key="container_arrival_history_sort",
    ) or "按到柜时间"
    group_by_department = sort_label == "按部门"
    sorted_df = sort_arrival_history_rows(
        raw_df,
        mode="department" if group_by_department else "time",
    )
    batches = build_arrival_batch_summary(sorted_df)
    container_keys = batches["货柜记录ID"].astype(str).tolist()
    widget_key = container_selection_widget_key(
        st.session_state, "arrival_history_batch_selection", container_keys
    )
    selected = st.dataframe(
        batches.drop(columns=["货柜记录ID"]),
        hide_index=True,
        width="stretch",
        height=fit_table_height(batches),
        on_select="rerun",
        selection_mode="single-row",
        key=widget_key,
        column_config={
            "实际到柜日期": st.column_config.DateColumn(
                "实际到柜日期", format="YYYY-MM-DD"
            ),
            "SKU数": st.column_config.NumberColumn("SKU数", format="%d"),
            "总件数": st.column_config.NumberColumn("总件数", format="%d"),
        },
    )
    container_key = selected_container_key(
        container_keys, selected.selection.rows
    )
    if not container_key:
        st.caption("点选一个到柜批次即可查看完整明细。")
        return sorted_df, None
    target = sorted_df[
        sorted_df["container_key"].astype(str).eq(str(container_key))
    ]
    render_container_detail(
        build_container_display(
            target, include_cost=has_permission("can_view_cost")
        ),
        container_key,
    )
    return sorted_df, container_key


def render_arrival_date_range(today):
    selected = st.date_input(
        "实际到柜日期",
        value=(today - timedelta(days=30), today),
        max_value=today,
        key="container_arrival_history_dates",
    )
    if isinstance(selected, (tuple, list)):
        if len(selected) >= 2:
            return selected[0], selected[1]
        if len(selected) == 1:
            return selected[0], selected[0]
    return selected, selected
