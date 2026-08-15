"""Logistics page controller."""

import streamlit as st

from ui.logistics.review.model import database_error
from ui.logistics.summary.view import render_logistics_summary
from ui.logistics.sync_view import render_sync
from ui.logistics.tracking import render_tracking_lookup
from utils.auth import has_permission


def render_logistics_page(supabase, selected_view="review"):
    can_manage = has_permission("can_manage_logistics")

    st.title("物流单号追踪")
    st.markdown(
        "- ERP + USPS：获取订单物流关系，核查物流事件和始发地点。\n"
        "- :red[**OCR**]：USPS不提供完整寄件地址和重量时，识别面单PDF或图片，"
        "辅助发现可疑面单。"
    )
    if selected_view == "review":
        _render_review_tab(supabase, can_manage)
    elif selected_view == "summary":
        render_logistics_summary(supabase, can_manage)
    else:
        _render_rules()


def _render_review_tab(supabase, can_manage):
    if can_manage:
        render_sync(supabase)
        st.divider()
    else:
        st.info(
            "主管账号可查询数据库记录和USPS实时状态；"
            "ERP同步、面单OCR及批量下载由售后或管理员处理。"
        )
    render_tracking_lookup(
        supabase,
        database_error,
        (
            st.session_state.get("logistics_usps_candidates", [])
            if can_manage else None
        ),
    )


def _render_rules():
    st.subheader("当前面单审核规则")
    st.write("寄件街道：25 Ranic Road")
    st.write("寄件州：New York")
    st.write("USPS状态：不能已有Pre-Shipment、Pre-Scan或后续记录")
    st.write("单件衣服参考重量：3–4 oz或略高；明显达到磅级进入调查")
    st.info(
        "地址和重量来自平台面单PDF OCR；"
        "平台未提供面单下载时会明确标记无法获取。"
    )
