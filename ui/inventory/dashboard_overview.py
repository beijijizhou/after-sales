"""Inventory dashboard overview and completion status table."""

from datetime import timedelta

import streamlit as st

from db.inventory.dashboard import build_daily_operation_table, load_inventory_overview


def render_overview(supabase, today):
    st.subheader("库存总览")
    try:
        overview = load_inventory_overview(supabase, today)
    except Exception as error:
        st.error(f"库存总览加载失败：{error}")
        return
    production, consumables, containers = st.columns(3)
    with production.container(border=True):
        st.markdown("#### 生产库存")
        left, right = st.columns(2)
        left.metric("库存件数", f"{overview['production_units']:,}")
        right.metric("缺货 SKU", overview["zero_stock_skus"])
        st.caption(f"共 {overview['production_skus']:,} 个 SKU")
        st.page_link("pages/4_库存.py", label="查看生产库存 →")
    with consumables.container(border=True):
        st.markdown("#### 耗材库存")
        left, right = st.columns(2)
        left.metric("启用 SKU", overview["consumable_skus"])
        right.metric("低库存", overview["low_consumable_skus"])
        st.caption("低库存按各耗材安全库存判断")
        st.page_link("pages/9_耗材库存.py", label="查看耗材库存 →")
    with containers.container(border=True):
        st.markdown("#### 货柜安排")
        first, second, third = st.columns(3)
        first.metric("在途", overview["in_transit_containers"])
        second.metric("7天到柜", overview["arriving_containers"])
        third.metric("延迟", overview["delayed_containers"])
        st.page_link("pages/5_货柜安排.py", label="查看货柜安排 →")


def render_completion_overview(
    summary, completed, today, start_date, history_end, check_days, missing,
):
    if check_days:
        st.caption(
            f"补录统计：{start_date:%Y-%m-%d} 至 {history_end:%Y-%m-%d}｜"
            f"共 {check_days} 个已结束日期"
        )
    else:
        st.caption("补录统计：暂无已经结束的日期")
    if missing:
        st.warning(f"四类出库合计还有 {missing} 个日期/项目需要处理。")
    else:
        st.success(f"截至 {history_end:%Y-%m-%d} 的四类出库全部完成。")
    requested_flow = render_operation_table(
        build_daily_operation_table(summary, completed, today)
    )
    st.caption("今日尚未结束，显示“进行中”属于正常进度，不计入待补日期。")
    return requested_flow


def render_operation_table(operation_table):
    widths = [1.25, 0.9, 0.8, 1.8, 0.8, 1.55, 0.85]
    headers = [
        "出库项目", "数据方式", "截止昨日", "待补日期",
        "今日状态", "当前操作", "补录入口",
    ]
    for column, label in zip(st.columns(widths), headers):
        column.markdown(f"**{label}**")
    requested_flow = None
    for row in operation_table.to_dict("records"):
        columns = st.columns(widths)
        values = [row[label] for label in headers[:6]]
        for column, value in zip(columns[:6], values):
            column.write(value)
        project = row["出库项目"]
        if row["待补日期"] == "无":
            columns[6].write("—")
        elif project == "黑白短袖":
            columns[6].page_link("pages/4_库存.py", label="去补录")
        elif project == "DTF 耗材":
            columns[6].page_link("pages/9_耗材库存.py", label="去补录")
        elif columns[6].button(
            "预览补录", key=f"inventory_dashboard_preview_{project}",
            width="stretch",
        ):
            requested_flow = project
    return requested_flow


def history_period(today, start_date):
    history_end = today - timedelta(days=1)
    return history_end, max((history_end - start_date).days + 1, 0)
