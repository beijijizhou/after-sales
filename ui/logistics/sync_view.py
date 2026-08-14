"""ERP and pasted-data synchronization views for logistics review."""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from automation.logistics import parse_logistics_frame
from automation.logistics.humbird import HUMBIRD_OPEN_LOGISTICS_PLATFORMS
from automation.production import (
    PLATFORMS_BY_DEPARTMENT,
    PRODUCTION_DEPARTMENTS,
    SDS_PLATFORM_PROFILES,
)
from ui.logistics.review.model import (
    classify_carrier_rows,
    default_logistics_platforms,
    is_target_usps_review,
    label_ocr_candidates,
    order_tracking_pairs,
)
from ui.logistics.review.state import reset_review_selection
from ui.logistics.review.view import render_carrier_review
from ui.logistics.source_gateway import (
    fetch_source,
    render_s2b_connection_status,
)
from utils.auth import has_permission


CONNECTED_PLATFORMS = {
    *HUMBIRD_OPEN_LOGISTICS_PLATFORMS,
    "S2B", "七创", "一朵云", *SDS_PLATFORM_PROFILES,
}
ORDER_STAGES = {
    "待排产/未接单": 1, "生产中": 2, "已完成/已发货": 6,
}


def render_sync(supabase):
    auto_tab, upload_tab = st.tabs(["从ERP自动读取", "复制粘贴订单物流"])
    with auto_tab:
        _render_erp_sync()
    with upload_tab:
        _render_upload_sync()
    st.divider()
    render_carrier_review(True)


def _render_erp_sync():
    st.subheader("从ERP读取订单与物流单号")
    columns = st.columns(2)
    department = columns[0].selectbox(
        "部门", PRODUCTION_DEPARTMENTS, key="logistics_department"
    )
    platforms = tuple(PLATFORMS_BY_DEPARTMENT.get(department, ()))
    selected = columns[1].multiselect(
        "生产平台", platforms,
        default=default_logistics_platforms(platforms, CONNECTED_PLATFORMS),
        key=f"logistics_platforms_{department}",
    )
    connected = [item for item in platforms if item in CONNECTED_PLATFORMS]
    pending = [item for item in platforms if item not in CONNECTED_PLATFORMS]
    st.caption(
        f"{department} 已配置平台：{'、'.join(platforms) or '暂无'}｜"
        f"已接入物流接口：{'、'.join(connected) or '暂无'}｜"
        f"尚未接入物流接口：{'、'.join(pending) or '无'}"
    )
    stage = st.selectbox("订单阶段", list(ORDER_STAGES))
    dates = st.columns(2)
    start_date = dates[0].date_input(
        "开始日期", value=date.today() - timedelta(days=1)
    )
    end_date = dates[1].date_input("结束日期", value=date.today())
    render_s2b_connection_status(selected)
    if not st.button(
        "从ERP读取数据", type="primary", disabled=not selected,
        width="stretch",
    ):
        return
    if not has_permission("can_manage_logistics"):
        st.error("当前账号没有同步物流数据的权限。")
        return
    _load_selected_sources(selected, department, stage, start_date, end_date)


def _load_selected_sources(selected, department, stage, start_date, end_date):
    all_rows, errors, reviewed_rows = [], [], []
    progress = st.progress(0)
    for index, source in enumerate(selected, start=1):
        try:
            rows = fetch_source(
                source, department, ORDER_STAGES[stage], start_date, end_date
            )
            for row in rows:
                row.update({
                    "local_acceptance_status": stage,
                    "department": department,
                })
            reviewed = classify_carrier_rows(rows)
            reviewed_rows.extend(reviewed)
            usps_rows = [
                item["row"] for item in reviewed
                if is_target_usps_review(item)
            ]
            all_rows.extend(usps_rows)
            st.write(
                f"{source}：读取 {len(rows):,} 条｜USPS {len(usps_rows):,} 条｜"
                f"可下载面单 {len(label_ocr_candidates(reviewed)):,} 张｜"
                f"已过滤 {len(rows) - len(usps_rows):,} 条"
            )
        except Exception as error:
            errors.append(f"{source}：{error}")
        progress.progress(index / len(selected))
    st.session_state["logistics_usps_candidates"] = order_tracking_pairs(all_rows)
    st.session_state["logistics_carrier_review_rows"] = reviewed_rows
    reset_review_selection()
    if all_rows:
        st.success(f"本次读取到 {len(all_rows):,} 条普通 USPS；结果未写入数据库。")
    if errors:
        st.warning("；".join(errors))


def _render_upload_sync():
    st.subheader("复制粘贴订单与物流单号")
    st.caption(
        "在Excel里复制两列，点击下方第一格后直接粘贴；"
        "第一列订单号，第二列物流单号。"
    )
    entry = st.data_editor(
        pd.DataFrame([{"订单号": "", "物流单号": ""}]),
        hide_index=True, num_rows="dynamic", width="stretch",
        column_config={
            "订单号": st.column_config.TextColumn("订单号", required=False),
            "物流单号": st.column_config.TextColumn("物流单号", required=False),
        }, key="logistics_order_tracking_paste",
    )
    rows, issues = parse_logistics_frame(entry)
    if not rows and not issues:
        st.info("填写后会先校验并进入“物流识别核对”，不会直接查询USPS。")
    if issues:
        st.error("导入已停止：" + "；".join(issues[:20]))
        if len(issues) > 20:
            st.caption(f"另有 {len(issues) - 20:,} 行错误未显示。")
        return
    st.caption(f"校验通过：{len(rows):,} 条订单物流记录。")
    if not st.button(
        "进行物流识别", type="primary", width="stretch", disabled=not rows,
    ):
        return
    if not has_permission("can_manage_logistics"):
        st.error("当前账号没有导入物流数据的权限。")
        return
    reviewed = classify_carrier_rows(rows)
    st.session_state["logistics_carrier_review_rows"] = reviewed
    st.session_state["logistics_usps_candidates"] = order_tracking_pairs([
        item["row"] for item in reviewed if is_target_usps_review(item)
    ])
    reset_review_selection()
    usps_count = sum(is_target_usps_review(item) for item in reviewed)
    st.success(
        f"已导入 {len(rows):,} 条｜普通USPS {usps_count:,} 条｜"
        f"其他物流 {len(rows) - usps_count:,} 条"
    )
