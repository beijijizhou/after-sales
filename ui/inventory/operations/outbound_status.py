from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from automation.sync.dtf_colored_inventory import (
    load_colored_day_deducted_total,
)
from db.inventory.operations.outbound_audit import (
    find_missing_outbound_dates,
    load_daily_outbound_dates,
    load_uv_daily_consumption_total,
)


def render_colored_daily_consumption_alert(supabase):
    today = datetime.now(ZoneInfo("America/New_York")).date()
    try:
        deducted = load_colored_day_deducted_total(supabase, today)
    except Exception:
        return
    if deducted:
        st.success(
            f"彩色短袖今日库存已扣减 {deducted:,} 件"
            "（来源：生产系统）。"
        )
    else:
        st.warning(
            "彩色短袖今日生产消耗尚未扣减；"
            "请到“消耗模型”读取并确认今日数据。"
        )


def render_uv_daily_consumption_alert(supabase):
    today = datetime.now(ZoneInfo("America/New_York")).date()
    try:
        deducted = load_uv_daily_consumption_total(supabase, today)
    except Exception:
        return
    if deducted:
        st.success(
            f"UV 今日库存消耗已扣减 {deducted:,} 件"
            "（来源：Google Sheets）。"
        )
    else:
        st.warning(
            "UV 今日库存消耗尚未扣减；请到“消耗模型”读取并确认今日数据。"
        )


def render_daily_outbound_alert(supabase, department, lookback_days=7):
    today = datetime.now(ZoneInfo("America/New_York")).date()
    start_date = today - timedelta(days=lookback_days - 1)
    try:
        recorded_dates = load_daily_outbound_dates(
            supabase, department, start_date, today
        )
    except Exception:
        return

    missing_dates = find_missing_outbound_dates(
        recorded_dates, start_date, today
    )
    previous_missing = [value for value in missing_dates if value < today]
    today_is_recorded = today in recorded_dates

    if previous_missing:
        labels = "、".join(
            f"{value:%m/%d}" for value in previous_missing
        )
        st.error(
            f"仓库每日出货待核对：最近 {lookback_days} 天缺少 "
            f"{labels} 的登记记录。"
        )
    if not today_is_recorded:
        st.warning("今日仓库出货尚未登记；完成出货后请确认保存。")
    elif not previous_missing:
        st.success("仓库每日出货记录完整，今日已登记。")
