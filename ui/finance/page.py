from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.finance import (
    load_container_finance_month,
    load_inventory_finance_month,
    load_inventory_value_snapshot,
    load_missing_inventory_cost_lots,
    load_pending_cost_batches,
)
from ui.finance.cost_editor import render_inbound_cost_editor
from ui.finance.inbound_batches import render_inbound_batch_browser
from ui.finance.pending_costs import render_pending_cost_batches
from ui.production_data.uv_monthly_summary import (
    render_uv_monthly_summary,
)
from ui.finance.reports import (
    build_two_week_daily_amounts as _build_two_week_daily_amounts,
    render_container_report as _render_container_report,
    render_cost_detail as _render_cost_detail,
    render_department_summary as _render_department_summary,
    render_inventory_filters as _render_inventory_filters,
    render_inventory_report as _render_inventory_report,
)


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_finance_page(supabase):
    st.title("财务")
    month = _render_month_selector()
    start_date, end_date = _month_range(month)
    report_date = _report_date(month, end_date)
    recent_start = report_date - timedelta(days=13)

    with st.spinner("正在汇总月度财务数据..."):
        finance_df = load_inventory_finance_month(
            supabase, start_date, end_date
        )
        if recent_start < start_date:
            recent_finance_df = load_inventory_finance_month(
                supabase, recent_start, report_date + timedelta(days=1)
            )
        else:
            recent_finance_df = finance_df[
                (pd.to_datetime(finance_df["date"]).dt.date >= recent_start)
                & (pd.to_datetime(finance_df["date"]).dt.date <= report_date)
            ].reset_index(drop=True)
        inventory_value_df = load_inventory_value_snapshot(supabase)
        missing_cost_df = load_missing_inventory_cost_lots(supabase)
        pending_cost_df = load_pending_cost_batches(supabase)
        container_df = load_container_finance_month(
            supabase, start_date, end_date
        )

    (
        inventory_tab,
        summary_tab,
        batch_tab,
        edit_tab,
        detail_tab,
        container_tab,
        uv_tab,
    ) = st.tabs([
        "商品库存月报",
        "部门 / 品类",
        "入库批次",
        "成本维护",
        "流水明细",
        "货柜采购",
        "UV生产月汇总",
    ])
    with inventory_tab:
        _render_inventory_report(
            finance_df, recent_finance_df,
            inventory_value_df, month, report_date,
        )
    with summary_tab:
        _render_department_summary(finance_df)
    with batch_tab:
        _render_inbound_batches(supabase, finance_df, pending_cost_df)
    with edit_tab:
        _render_cost_maintenance(
            supabase, finance_df, missing_cost_df, pending_cost_df
        )
    with detail_tab:
        _render_cost_detail(finance_df)
    with container_tab:
        _render_container_report(container_df, month)
    with uv_tab:
        render_uv_monthly_summary(default_month=month)


def _render_month_selector():
    today = date.today()
    try:
        today = pd.Timestamp.now(tz=NY_TIMEZONE).date()
    except Exception:
        pass
    months = []
    for offset in range(24):
        total = today.year * 12 + today.month - 1 - offset
        months.append(date(total // 12, total % 12 + 1, 1))
    return st.selectbox(
        "查看月份",
        months,
        format_func=lambda value: f"{value.year}年{value.month}月",
    )


def _month_range(month):
    total = month.year * 12 + month.month
    return month, date(total // 12, total % 12 + 1, 1)


def _report_date(month, end_date):
    today = pd.Timestamp.now(tz=NY_TIMEZONE).date()
    if month.year == today.year and month.month == today.month:
        return today
    return end_date - timedelta(days=1)


def _render_inbound_batches(supabase, finance_df, pending_cost_df):
    render_pending_cost_batches(pending_cost_df)
    batch_rows = _render_inventory_filters(
        finance_df, key="finance_batch_filters"
    )
    render_inbound_batch_browser(batch_rows)


def _render_cost_maintenance(
    supabase, finance_df, missing_cost_df, pending_cost_df,
):
    editor_source = pd.concat(
        [missing_cost_df, finance_df], ignore_index=True
    ).drop_duplicates(subset=["record_id"], keep="first")
    edit_rows = _render_inventory_filters(
        editor_source, key="finance_cost_edit_filters"
    )
    missing_lots = int(edit_rows["missing_cost"].sum()) if not edit_rows.empty else 0
    if missing_lots:
        st.info(
            f"当前筛选范围有 {missing_lots:,} 个批次缺少成本，已排在最前面。"
        )
    render_inbound_cost_editor(supabase, edit_rows)
