"""Render and confirm automatic daily deduction batch previews."""

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from automation.sync.daily_inventory_consumption import (
    AUTOMATIC_DAILY_FLOWS,
    apply_automatic_daily_batch_previews,
    build_automatic_daily_batch_summary,
)
from db.inventory.dashboard import load_daily_completion_status
from utils.auth import get_current_operator_name, has_permission
from ui.inventory.operations.system_deduction import (
    system_deduction_comparison,
    system_deduction_display,
)
from ui.operations import render_stock_change_review


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_batch_preview(supabase, previews, state_key, identity_key):
    labels = {
        "ready": "待确认", "completed": "已完成", "blocked": "存在问题",
        "error": "读取失败", "no_data": "无数据",
    }
    summary = build_automatic_daily_batch_summary(previews)
    display = summary.copy()
    display["状态"] = display["状态"].map(labels).fillna(display["状态"])
    st.subheader("批量补扣预览")
    st.dataframe(
        display, hide_index=True, width="stretch",
        column_config={
            "日期": st.column_config.DateColumn("日期"),
            "预计扣减": st.column_config.NumberColumn("预计扣减", format="%d 件"),
            "来源总量": st.column_config.NumberColumn("来源总量", format="%d 件"),
            "待核对差额": st.column_config.NumberColumn("待核对差额", format="%d 件"),
            "数据范围": st.column_config.TextColumn("数据范围", width="large"),
            "说明": st.column_config.TextColumn("说明", width="large"),
        },
    )
    ready = _preview_items(previews, ready_only=True)
    for movement_date, flow, preview in _preview_items(previews):
        render_preview_detail(movement_date, flow, preview)
    if not ready:
        st.info("当前没有需要扣减的系统数据。")
        return
    if not has_permission("can_edit_inventory"):
        st.info("当前账号只有查看权限，不能扣减库存。")
        return
    total = sum(preview.quantity for _, _, preview in ready)
    confirmed = st.checkbox(
        f"我已核对 {len(ready)} 个日期/项目，确认共扣减 {total:,} 件",
        key="inventory_dashboard_auto_confirm",
    )
    if not st.button(
        "一键补扣全部已预览库存", type="primary", width="stretch",
        disabled=not confirmed, key="inventory_dashboard_auto_apply",
    ):
        return
    _apply_batch(supabase, previews, state_key, identity_key)


def render_preview_detail(movement_date, flow, preview):
    with st.expander(
        f"{movement_date:%Y-%m-%d}｜{flow.label}｜预计扣减 {preview.quantity:,} 件"
    ):
        if preview.message:
            st.info(preview.message)
        if preview.source_rows is not None:
            st.markdown("**平台来源核对**")
            st.caption(
                f"原始生产 {preview.source_quantity:,} 件｜"
                f"可扣库存 {preview.quantity:,} 件｜"
                f"待核对 {preview.unresolved_quantity:,} 件"
            )
            st.dataframe(preview.source_rows, hide_index=True, width="stretch")
            st.markdown("**SKU 库存匹配**")
        comparison = system_deduction_comparison(preview.rows)
        identity_columns = [
            column for column in [
                "状态", "生产平台", "表格产品", "品类", "材质",
                "品牌", "颜色", "尺码", "型号",
            ] if column in comparison
        ]
        extra_columns = [
            column for column in ["待处理数量", "未扣数量", "当日消耗"]
            if column in comparison
        ]
        render_stock_change_review(
            comparison,
            action="出库",
            title="SKU 库存扣减核对",
            identity_columns=identity_columns,
            extra_columns=extra_columns,
            unit="件",
            quantity_format="%d",
        )


def _preview_items(previews, ready_only=False):
    items = []
    for movement_date in sorted(previews):
        for flow in AUTOMATIC_DAILY_FLOWS:
            preview = previews[movement_date].get(flow.code)
            if preview is None:
                continue
            if ready_only and preview.state != "ready":
                continue
            if not ready_only and preview.rows.empty and preview.source_rows is None:
                continue
            items.append((movement_date, flow, preview))
    return items


def _apply_batch(supabase, previews, state_key, identity_key):
    results, errors = apply_automatic_daily_batch_previews(
        supabase, previews, get_current_operator_name()
    )
    labels = {flow.code: flow.label for flow in AUTOMATIC_DAILY_FLOWS}
    if results:
        try:
            _, completed, _ = load_daily_completion_status(
                supabase, datetime.now(NY_TIMEZONE).date()
            )
        except Exception:
            completed = {}
        details = "；".join(
            format_applied_result(
                movement_date, code, labels[code], quantity, completed
            )
            for (movement_date, code), quantity in results.items()
        )
        st.session_state["inventory_dashboard_saved_message"] = (
            f"系统库存补扣完成，完成状态已重新核对：{details}"
        )
    if errors:
        st.session_state["inventory_dashboard_error_message"] = "；".join(
            f"{movement_date:%m/%d} {labels[code]}：{message}"
            for (movement_date, code), message in errors.items()
        )
    st.session_state.pop(state_key, None)
    st.session_state.pop(identity_key, None)
    st.rerun()


def format_applied_result(movement_date, code, label, quantity, completed):
    status = (
        "已完成" if movement_date in set(completed.get(code, set()))
        else "仍有待处理数据"
    )
    return f"{movement_date:%m/%d} {label} {quantity:,} 件（{status}）"


def system_stock_change_display(rows):
    return system_deduction_display(rows)
