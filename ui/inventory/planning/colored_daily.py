"""Colored-shirt daily production deduction form."""

import pandas as pd
import streamlit as st

from automation.sync.dtf_colored_inventory import (
    apply_colored_daily_deduction,
    build_colored_daily_preview,
    load_colored_day_deducted_total,
)
from ui.inventory.planning.colored_review import stock_change_comparison
from ui.operations import render_stock_change_review
from utils.auth.session import get_current_operator_name, has_permission


def render_colored_daily_deduction_form(supabase, current_date):
    st.subheader("彩色短袖系统库存扣减")
    st.caption(
        "从全部衣服平台读取当天生产数据；按纽约日期生成批次，"
        "重复确认不会重复扣减。"
    )
    state_key = "colored_daily_deduction_preview"
    date_key = "colored_daily_deduction_date"
    deducted = load_colored_day_deducted_total(supabase, current_date)
    if deducted:
        st.success(f"今日彩色短袖库存已扣减 {deducted:,} 件。")
        return
    if st.button("读取今日生产并生成扣减表", key="colored_daily_load"):
        try:
            preview = build_colored_daily_preview(supabase, current_date)
            st.session_state[state_key] = preview
            st.session_state[date_key] = current_date
        except Exception as error:
            st.error(f"读取今日生产失败：{error}")
    preview = st.session_state.get(state_key)
    if preview is None or st.session_state.get(date_key) != current_date:
        return
    if preview.empty:
        st.info(f"{current_date:%m/%d} 暂无完整的彩色短袖生产数据")
        return
    render_stock_change_review(
        stock_change_comparison(preview),
        action="出库",
        title="彩色短袖扣减库存核对",
        identity_columns=[
            "状态", "生产平台", "原始生产颜色", "原始生产尺码",
            "材质", "品牌", "颜色", "尺码",
        ],
        extra_columns=["待处理数量"],
        unit="件",
        quantity_format="%d",
    )
    deferred = preview[preview["状态"] != "可扣减"]
    if not deferred.empty:
        st.warning(
            f"有 {int(deferred['未扣数量'].sum()):,} 件因库存为 0 或字段异常暂不扣减；"
            "生产消耗仍会进入模型，待清点后再处理库存差异。"
        )
    total = int(pd.to_numeric(
        preview.loc[preview["状态"] == "可扣减", "预计扣减"],
        errors="coerce",
    ).fillna(0).sum())
    st.caption(f"本次实际可扣减：{total:,} 件；库存最低扣到 0。")
    if not has_permission("can_edit_inventory"):
        st.info("当前账号只有查看权限，不能确认扣减库存。")
        return
    confirmed = st.checkbox(
        "我已核对生产数据和待清点差异",
        key="colored_daily_confirm",
    )
    if not st.button(
        "确认扣减今日彩色短袖库存", type="primary",
        disabled=not confirmed, key="colored_daily_apply",
    ):
        return
    try:
        imported = apply_colored_daily_deduction(
            supabase, preview, current_date, get_current_operator_name()
        )
    except Exception as error:
        st.error(f"扣减失败：{error}")
        return
    st.session_state.pop(state_key, None)
    st.session_state.pop(date_key, None)
    st.session_state["inventory_saved_message"] = (
        f"彩色短袖生产库存已扣减 {imported:,} 件"
    )
    st.rerun()
