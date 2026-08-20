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
from ui.inventory.container.tables import render_container_detail
from ui.table_layout import fit_table_height
from utils.auth import has_permission


ARRIVAL_STATUSES = {"未到货", "延迟", "在途"}


def filter_editable_container_search_rows(raw_df):
    """Keep only containers that still belong to the transit-edit workflow."""
    if raw_df.empty or "status" not in raw_df.columns:
        return raw_df.iloc[0:0].copy()
    status = raw_df["status"].fillna("").astype(str).str.strip()
    eligible_rows = raw_df[status.isin(ARRIVAL_STATUSES)]
    eligible_keys = set(eligible_rows["container_key"].astype(str))
    ineligible_keys = set(
        raw_df.loc[~status.isin(ARRIVAL_STATUSES), "container_key"].astype(str)
    )
    eligible_keys -= ineligible_keys
    return raw_df[
        raw_df["container_key"].astype(str).isin(eligible_keys)
    ].reset_index(drop=True)


def build_container_search_choices(raw_df):
    if raw_df.empty:
        return {}
    choices = {}
    for key, rows in raw_df.groupby("container_key", sort=False):
        row = rows.iloc[0].to_dict()
        key = row["container_key"]
        raw_number = row.get("container_no")
        number = str(raw_number).strip() if _has_value(raw_number) else ""
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


def filter_container_search_choices(raw_df, choices, search_text):
    """Filter container choices by physical number, business name or context."""
    term = "".join(str(search_text or "").casefold().split())
    if not term or raw_df.empty:
        return choices
    matched = {}
    for container_key, label in choices.items():
        rows = raw_df[raw_df["container_key"].astype(str) == str(container_key)]
        searchable_columns = [
            "container_key", "container_no", "note", "department", "category",
        ]
        values = [label]
        for column in searchable_columns:
            if column in rows.columns:
                values.extend(rows[column].dropna().astype(str).tolist())
        haystack = "".join("".join(value.casefold().split()) for value in values)
        if term in haystack:
            matched[container_key] = label
    return matched


def render_container_search(supabase):
    st.subheader("查找与修改货柜")
    st.caption(
        "这里只查找和修改仍在运输中的货柜。已到柜货柜前往“待确认入库”；"
        "已入库货柜前往“到柜及入库历史”，数量、成本与撤销在库存批次处理。"
    )
    saved = st.session_state.pop("container_undo_saved", None)
    if saved:
        st.success(saved)
    try:
        all_rows = load_container_search_records(supabase)
    except Exception as error:
        st.error(f"货柜列表加载失败：{error}")
        return
    raw_df = filter_editable_container_search_rows(all_rows)
    if raw_df.empty:
        st.info("当前没有仍在运输中的货柜")
        st.session_state.pop("container_search_dropdown", None)
        return
    choices = build_container_search_choices(raw_df)
    search_text = st.text_input(
        "货柜号或备注搜索",
        key="container_search_text",
        placeholder="输入实体货柜号、例如 COSU6502384810，或输入第十四柜",
    )
    visible_choices = filter_container_search_choices(
        raw_df, choices, search_text
    )
    if str(search_text or "").strip() and not visible_choices:
        _render_search_scope_message(all_rows, search_text)
        st.session_state.pop("container_search_dropdown", None)
        return
    search_options = ["", *visible_choices]
    _reset_invalid_selectbox("container_search_dropdown", search_options)
    st.caption(
        "搜索支持实体货柜号、业务备注名称、部门和品类；"
        "结果优先显示业务备注名称。"
    )
    container_key = st.selectbox(
        "选择匹配货柜",
        search_options,
        format_func=lambda value: (
            "请选择货柜" if not value else visible_choices[value]
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


def _render_search_scope_message(all_rows, search_text):
    term = str(search_text or "").strip()
    all_choices = build_container_search_choices(all_rows)
    matches = filter_container_search_choices(
        all_rows, all_choices, term
    )
    if not matches:
        st.warning(f"未找到货柜：{term}")
        st.caption("数据库中没有匹配记录；如为新货柜，请前往“新增货柜”录入。")
        return
    matched = all_rows[
        all_rows["container_key"].astype(str).isin(
            {str(key) for key in matches}
        )
    ]
    statuses = set(
        matched["status"].fillna("").astype(str).str.strip()
    )
    if statuses == {"已到柜"}:
        st.info(f"{term} 已到柜，请前往“待确认入库”处理。")
        return
    if statuses and statuses.issubset({"已入库", "已到货"}):
        st.info(
            f"{term} 已入库，请前往“到柜及入库历史”查看；"
            "修改请前往库存的“批次修改与撤销”。"
        )
        return
    st.warning(f"{term} 当前状态不一致，请前往“到柜及入库历史”核对。")


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
        st.info(
            "这里展示的是该货柜的入库批次明细，不是当前剩余库存。"
            "需要修改数量、成本或撤销入库时，"
            "请前往“库存 → 批次修改与撤销”，选择“货柜入库”。"
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
