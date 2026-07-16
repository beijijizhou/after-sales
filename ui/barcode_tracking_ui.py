from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from db.barcode_operation_tracking import (
    build_barcode_histories_for_date,
    build_pending_operation_history,
)


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_operation_tracking_section():
    st.divider()
    st.subheader("问题订单追踪与历史")

    today = datetime.now(NY_TIMEZONE).date()
    date_col1, date_col2 = st.columns(2)
    start_date = date_col1.date_input("开始日期", value=today, max_value=today)
    end_date = date_col2.date_input("结束日期", value=today, max_value=today)
    if start_date > end_date:
        st.warning("开始日期不能晚于结束日期")
        return

    start_at = datetime.combine(start_date, time.min, tzinfo=NY_TIMEZONE)
    end_at = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=NY_TIMEZONE)
    st.caption("日期仅筛选完整操作历史；待处理订单始终显示全部未完成记录。")

    try:
        pending_df = build_pending_operation_history()
        tracking_df = build_barcode_histories_for_date(start_at, end_at)
    except Exception as error:
        st.error(f"追踪数据加载失败：{error}")
        st.info("请先在 Supabase SQL Editor 运行 sql/barcode_operation_history.sql")
        return

    pending_tab, history_tab = st.tabs(["待处理订单", "每个条码完整操作历史"])
    with pending_tab:
        if pending_df.empty:
            st.success("当前没有待重新出库的订单")
        else:
            pending_style = pending_df.style.apply(
                lambda row: ["background-color: #ffebee; color: #b71c1c"] * len(row),
                axis=1,
            )
            st.dataframe(pending_style, hide_index=True, width="stretch")

    with history_tab:
        if tracking_df.empty:
            st.info("所选日期内没有问题订单记录")
        else:
            st.dataframe(tracking_df, hide_index=True, width="stretch")
