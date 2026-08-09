import pandas as pd
import streamlit as st

from ui.inventory.shared.filters import _reset_invalid_selectbox

from db.inventory.container.repository import load_inventory_containers
from db.inventory.container.workflow import post_container_inventory
from ui.inventory.container.posting import render_container_posting_stock_review
from ui.inventory.container.tables import (
    render_container_inventory_summary,
    render_container_records,
)
from utils.auth import get_current_operator_name, has_permission


def container_tab_names(has_today_arrivals, has_pending_posting=False):
    names = []
    if has_pending_posting:
        names.append("待确认入库")
    if has_today_arrivals:
        names.append("今日到柜")
    names.extend(["在途货柜", "新增货柜", "到柜及入库历史"])
    if not has_today_arrivals:
        names.append("今日到柜")
    if not has_pending_posting:
        names.append("待确认入库")
    return names


def load_today_arrivals(
    supabase, today, department, category,
    brands, materials, colors, sizes,
):
    return load_inventory_containers(
        supabase,
        start_date=today,
        end_date=today,
        department=department,
        category=category,
        statuses=["已到柜", "已入库", "已到货"],
        date_field="actual_arrival_date",
        brands=brands,
        materials=materials,
        colors=colors,
        sizes=sizes,
    )


def render_today_arrivals(raw_df, load_error=None):
    st.subheader("今日到柜")
    st.caption("这里只显示仓库已确认、且真实到柜日期为今天的货柜。")
    if load_error is not None:
        error = load_error
        st.error(f"今日到柜加载失败：{error}")
        return
    if raw_df.empty:
        st.info("今天还没有手动确认到柜的货柜")
        return

    quantities = pd.to_numeric(
        raw_df["quantity"], errors="coerce"
    ).fillna(0)
    col1, col2 = st.columns(2)
    col1.metric("今日到柜", raw_df["container_key"].nunique())
    col2.metric("今日到柜总件数", int(quantities.sum()))
    render_container_inventory_summary(
        raw_df, "今日到柜库存汇总"
    )
    render_container_records(
        raw_df,
        include_cost=has_permission("can_view_cost"),
    )


def render_today_arrival_posting(supabase, raw_df):
    if raw_df.empty:
        return
    pending = raw_df[raw_df["status"] == "已到柜"].copy()
    st.subheader("确认入库")
    if pending.empty:
        st.success("今日到柜均已入库")
        return
    if not has_permission("can_edit_container"):
        st.info("当前账号可以查看，但不能确认入库")
        return

    pending["quantity"] = pd.to_numeric(
        pending["quantity"], errors="coerce"
    ).fillna(0)
    summary = (
        pending.groupby(
            ["container_key", "container_no"],
            dropna=False,
            as_index=False,
        )["quantity"]
        .sum()
    )
    choices = {}
    for row in summary.to_dict("records"):
        container_key = row["container_key"]
        number = row.get("container_no") or container_key
        quantity = int(row["quantity"])
        choices[f"{number}｜{quantity:,} 件"] = container_key
    choice_labels = list(choices)
    _reset_invalid_selectbox("today_arrival_posting_target", choice_labels)
    selected = st.selectbox(
        "选择待入库货柜",
        choice_labels,
        key="today_arrival_posting_target",
    )
    container_key = choices[selected]
    total = int(
        pd.to_numeric(
            pending.loc[
                pending["container_key"] == container_key,
                "quantity",
            ],
            errors="coerce",
        ).fillna(0).sum()
    )
    note = st.text_input(
        "入库备注",
        key=f"today_arrival_posting_note_{container_key}",
    )
    target = pending[pending["container_key"] == container_key]
    render_container_posting_stock_review(supabase, target)
    st.warning(f"确认后库存将增加 {total:,} 件")
    if not st.button(
        "确认入库",
        type="primary",
        width="stretch",
        key=f"today_arrival_posting_{container_key}",
    ):
        return
    try:
        post_container_inventory(
            supabase,
            container_key,
            get_current_operator_name(),
            note,
        )
        st.success(f"入库成功：库存增加 {total:,} 件")
        st.toast("货柜已完成入库")
        st.rerun()
    except Exception as error:
        st.error(f"确认入库失败：{error}")
