import pandas as pd
import streamlit as st

from ui.inventory.shared.filters import _reset_invalid_selectbox

from db.inventory.container.history import (
    build_container_history_display,
    load_container_events,
)
from db.inventory.container.repository import load_container_search_records
from db.inventory.container.labels import get_container_display_label
from db.inventory.container.tables import build_container_display
from ui.inventory.container.events import render_status_update
from ui.inventory.container.item_editor import (
    render_posted_container_correction,
)
from ui.inventory.container.posting import render_container_posting_action
from ui.inventory.container.reversal import render_container_undo_action
from ui.inventory.container.tables import render_container_detail
from ui.table_layout import fit_table_height
from utils.auth import has_permission


ARRIVAL_STATUSES = {"未到货", "延迟", "在途"}


def build_container_search_choices(raw_df):
    if raw_df.empty:
        return {}
    choices = {}
    for key, rows in raw_df.groupby("container_key", sort=False):
        row = rows.iloc[0].to_dict()
        key = row["container_key"]
        number = row.get("container_no") or ""
        notes = rows.get("note", pd.Series(dtype=str)).tolist()
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
            f"{get_container_display_label(key, number, notes)}｜{status}"
            f"{date_text}{business_text}｜{total:,} 件"
        )
    return choices


def render_container_search(supabase):
    saved = st.session_state.pop("container_undo_saved", None)
    if saved:
        st.success(saved)
    try:
        raw_df = load_container_search_records(supabase)
    except Exception as error:
        st.error(f"货柜列表加载失败：{error}")
        return
    if raw_df.empty:
        st.info("目前还没有货柜记录")
        return
    choices = build_container_search_choices(raw_df)
    search_options = ["", *choices]
    _reset_invalid_selectbox("container_search_dropdown", search_options)
    st.caption("优先显示货柜备注名称；实体货柜号作为辅助，也可以输入柜号、部门或品类查找。")
    container_key = st.selectbox(
        "查找货柜",
        search_options,
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
    _render_search_action(supabase, target, container_key)
    _render_search_history(supabase, container_key)


def _has_value(value):
    return value is not None and not pd.isna(value) and str(value).strip()


def get_container_search_action(raw_df):
    if raw_df.empty or "status" not in raw_df.columns:
        return None
    statuses = set(
        raw_df["status"].fillna("").astype(str).str.strip()
    ) - {""}
    if statuses and statuses.issubset(ARRIVAL_STATUSES):
        return "arrival"
    if statuses == {"已到柜"}:
        return "posting"
    if statuses.issubset({"已入库", "已到货"}) and statuses:
        return "completed"
    return "inconsistent"


def _render_search_action(supabase, target, container_key):
    action = get_container_search_action(target)
    if action == "completed":
        st.success("这个货柜已经完成入库")
        if has_permission("can_edit_container"):
            with st.expander("入库后更正与撤销", expanded=True):
                render_posted_container_correction(
                    supabase, target, container_key
                )
                st.divider()
                render_container_undo_action(
                    supabase, target, container_key, "container_search",
                    embedded=True,
                )
        return
    if action == "inconsistent":
        st.warning("这个货柜的明细状态不一致，请先核对货柜数据。")
        return
    if not has_permission("can_edit_container"):
        st.info("当前账号可以查看货柜，但不能确认到柜或入库")
        return
    if action == "arrival":
        render_status_update(
            supabase, target, container_key,
            key_prefix="container_search_status",
        )
    elif action == "posting":
        st.subheader("确认入库")
        render_container_posting_action(
            supabase, target, container_key,
            key_prefix="container_search_posting",
        )
        render_container_undo_action(
            supabase, target, container_key, "container_search"
        )


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
        height=fit_table_height(history),
        column_config={
            "事件日期": st.column_config.DateColumn("事件日期"),
            "备注": st.column_config.TextColumn("备注", width="large"),
        },
    )
