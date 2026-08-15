"""Logistics summary page view."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.logistics import load_logistics_summary_data
from ui.logistics.review.model import database_error
from ui.logistics.summary.detail import build_platform_activity_detail
from ui.logistics.summary.model import build_daily_platform_summary


NEW_YORK = ZoneInfo("America/New_York")


def render_logistics_summary(supabase, can_manage):
    st.subheader("物流数据总结")
    st.caption(
        "按纽约业务日期汇总ERP订单读取、USPS查询、面单PDF和OCR记录；"
        "先看平台汇总，再选择一行查看订单级明细。"
    )
    today = datetime.now(NEW_YORK).date()
    dates = st.columns(2)
    start_date = dates[0].date_input(
        "开始日期", value=today - timedelta(days=1),
        key="logistics_summary_start_date",
    )
    end_date = dates[1].date_input(
        "结束日期", value=today,
        key="logistics_summary_end_date",
    )
    if start_date > end_date:
        st.error("开始日期不能晚于结束日期。")
        return
    try:
        shipments, checks, sources, reviews = load_logistics_summary_data(
            supabase, start_date, end_date
        )
    except Exception as error:
        st.error(database_error(error))
        return
    summary = build_daily_platform_summary(
        shipments, checks, sources, reviews
    )
    if summary.empty:
        st.info("当前日期范围内没有物流读取或USPS查询记录。")
        return
    _render_metrics(summary)
    st.dataframe(summary, hide_index=True, width="stretch")
    selected = _select_summary_row(summary)
    detail = build_platform_activity_detail(
        selected, shipments, checks, sources, reviews
    )
    st.markdown("#### 订单与物流明细")
    if detail.empty:
        st.info("这个汇总范围暂时没有可显示的订单级明细。")
        return
    visible = [
        "记录时间", "记录类型", "部门", "平台", "ERP账号", "ERP订单号",
        "商户订单号", "物流单号", "物流商", "USPS状态", "查询用户",
        "查询错误", "面单PDF", "OCR状态", "OCR地址", "OCR重量（oz）",
    ]
    if not can_manage:
        visible = [
            column for column in visible
            if column not in {"面单PDF", "OCR地址", "OCR重量（oz）"}
        ]
    st.dataframe(
        detail[[column for column in visible if column in detail]],
        hide_index=True, width="stretch",
        column_config={
            "面单PDF": st.column_config.LinkColumn(display_text="打开面单"),
            "记录时间": st.column_config.DatetimeColumn(
                "记录时间", format="YYYY-MM-DD HH:mm:ss"
            ),
        },
    )


def _render_metrics(summary):
    metrics = st.columns(5)
    metrics[0].metric("平台日期组合", f"{len(summary):,}")
    metrics[1].metric("ERP订单", f"{summary['ERP订单数'].sum():,}")
    metrics[2].metric("USPS查询单号", f"{summary['USPS查询单号'].sum():,}")
    metrics[3].metric("PDF面单", f"{summary['PDF面单数'].sum():,}")
    metrics[4].metric("OCR已识别", f"{summary['OCR记录数'].sum():,}")


def _select_summary_row(summary):
    options = list(summary.index)
    selected_index = st.selectbox(
        "查看哪一组明细",
        options,
        format_func=lambda index: _summary_label(summary.loc[index]),
        key="logistics_summary_detail_scope",
    )
    return summary.loc[selected_index].to_dict()


def _summary_label(row):
    date_value = pd.to_datetime(row["日期"], errors="coerce")
    date_text = (
        date_value.strftime("%Y-%m-%d") if not pd.isna(date_value) else "未知日期"
    )
    return (
        f"{date_text}｜{row['部门']}｜{row['平台']}｜{row['ERP账号']}｜"
        f"ERP {int(row['ERP订单数']):,}｜USPS {int(row['USPS查询单号']):,}"
    )
