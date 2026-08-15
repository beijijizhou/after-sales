"""USPS tracking lookup controller."""

import pandas as pd
import streamlit as st

from db.logistics import ensure_tracking_context_shipments

from ui.logistics.tracking.input import (
    normalize_suggested_rows,
    parse_order_tracking_table,
)
from ui.logistics.tracking.labels import (
    extract_live_label_details,
    merge_label_details,
)
from ui.logistics.tracking.origin_view import (
    apply_usps_origin_fallback,
    render_raw_responses,
    render_results,
    render_tracking_events,
)
from ui.logistics.tracking.query import query_usps, tracking_query_plan
from ui.logistics.usps_usage import render_usps_usage
from utils.auth import get_current_operator_name


def render_tracking_lookup(supabase, database_error, suggested_numbers=None):
    st.subheader("使用USPS官方API核查")
    suggested_rows = normalize_suggested_rows(suggested_numbers)
    use_suggested = _render_suggested_toggle(suggested_rows)
    edited = _render_tracking_editor(use_suggested)
    query_mode = st.radio(
        "查询方式",
        ("数据库优先，缺失或过期再查USPS", "强制刷新USPS实时接口"),
        horizontal=True, key="logistics_tracking_query_mode",
    )
    context = pd.DataFrame(
        suggested_rows if use_suggested else parse_order_tracking_table(edited)
    )
    numbers = list(dict.fromkeys(
        context.get("物流单号", pd.Series(dtype=str)).astype(str)
    ))
    if not st.button(
        "开始查询", type="primary", disabled=not numbers,
        key="logistics_tracking_lookup_submit",
    ):
        render_usps_usage(supabase, database_error)
        st.info("粘贴物流单号后点击查询；实际提交给USPS的响应会保存到数据库。")
        return
    _execute_lookup(
        supabase, database_error, context, numbers,
        query_mode == "强制刷新USPS实时接口",
    )


def _render_suggested_toggle(suggested_rows):
    use_suggested = False
    if suggested_rows:
        use_suggested = st.checkbox(
            f"使用上方获取的 {len(suggested_rows):,} 条订单物流记录",
            value=True, key="logistics_use_acquired_usps_numbers",
        )
    st.caption(
        "默认使用上方ERP读取的普通USPS单号；也可以取消勾选，"
        "在下方表格手工输入或从 Excel / Google Sheets 粘贴整列。"
    )
    return use_suggested


def _render_tracking_editor(disabled):
    edited = st.data_editor(
        pd.DataFrame([{"订单号": "", "物流单号": ""}]),
        num_rows="dynamic", hide_index=True, width="stretch",
        key="logistics_tracking_lookup_table", disabled=disabled,
        column_config={
            "订单号": st.column_config.TextColumn(
                "订单号", help="与物流单号保持在同一行"
            ),
            "物流单号": st.column_config.TextColumn(
                "物流单号", help="支持直接粘贴订单号和物流单号两列"
            ),
        },
    )
    st.caption(
        "USPS Tracking响应会保存到数据库；默认优先使用一小时内的"
        "数据库记录，缺失或过期时再请求USPS。本区域不会启动OCR。"
    )
    return edited


def _execute_lookup(supabase, database_error, context, numbers, force_usps):
    try:
        source_shipments = ensure_tracking_context_shipments(
            supabase, context.to_dict("records"), get_current_operator_name()
        )
    except Exception as error:
        st.error(database_error(error))
        return
    cached, pending = tracking_query_plan(
        supabase, numbers, force_usps, database_error
    )
    fresh_rows = query_usps(
        pending, supabase, database_error,
        source_shipments=source_shipments,
    )
    render_usps_usage(supabase, database_error)
    if fresh_rows is None and cached.empty:
        return
    display = _combine_results(cached, fresh_rows, context)
    summary = st.columns(3)
    summary[0].metric("输入面单号", len(numbers))
    summary[1].metric("数据库返回", len(cached))
    summary[2].metric("USPS 接口请求", len(pending))
    display = apply_usps_origin_fallback(display)
    render_results(display)
    render_tracking_events(display)
    render_raw_responses(display)


def _combine_results(cached, fresh_rows, context):
    cached = cached.copy()
    if not cached.empty:
        cached["数据来源"] = "数据库缓存"
    fresh = pd.DataFrame(fresh_rows or [])
    if not fresh.empty:
        fresh["数据来源"] = "USPS 实时接口"
    display = pd.concat([cached, fresh], ignore_index=True)
    if not display.empty:
        display["USPS查询说明"] = display["has_postal_record"].map({
            True: "USPS已返回物流状态与Tracking Events",
            False: "USPS未发现物流记录",
        })
    if not context.empty:
        display = context.rename(columns={
            "物流单号": "tracking_number",
        }).merge(display, on="tracking_number", how="left")
    labels = extract_live_label_details(context)
    if not labels.empty and "面单PDF" in labels:
        labels = labels.drop(columns=["面单PDF"])
    return merge_label_details(display, labels)
