from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.finance import (
    build_container_summary,
    build_daily_summary,
    build_department_summary,
    build_finance_overview,
    build_inventory_value_overview,
    load_container_finance_month,
    load_inventory_finance_month,
    load_inventory_value_snapshot,
    load_missing_inventory_cost_lots,
)
from ui.finance.cost_editor import render_inbound_cost_editor
from ui.finance.inbound_batches import render_inbound_batch_browser
from ui.inventory.shared import (
    filter_inventory_rows,
    render_inventory_dimension_filters,
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
    ) = st.tabs([
        "商品库存月报",
        "部门 / 品类",
        "入库批次",
        "成本维护",
        "流水明细",
        "货柜采购",
    ])
    with inventory_tab:
        _render_inventory_report(
            supabase, finance_df, recent_finance_df,
            inventory_value_df, month, report_date,
        )
    with summary_tab:
        _render_department_summary(finance_df)
    with batch_tab:
        _render_inbound_batches(finance_df)
    with edit_tab:
        _render_cost_maintenance(supabase, finance_df, missing_cost_df)
    with detail_tab:
        _render_cost_detail(finance_df)
    with container_tab:
        _render_container_report(container_df, month)


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


def _render_inventory_report(
    supabase, finance_df, recent_finance_df,
    inventory_value_df, month, report_date,
):
    st.caption(
        f"{month.year}年{month.month}月 · 金额为库存成本，不是销售额"
    )
    overview = build_finance_overview(finance_df)
    inventory_value = build_inventory_value_overview(inventory_value_df)
    columns = st.columns(3)
    columns[0].metric(
        "当前库存成本", f"${inventory_value['inventory_value']:,.2f}"
    )
    columns[1].metric("本月入库金额", f"${overview['inbound_amount']:,.2f}")
    columns[2].metric("本月出库成本", f"${overview['outbound_amount']:,.2f}")

    missing = (
        overview["missing_inbound_quantity"]
        + overview["missing_outbound_quantity"]
    )
    if missing:
        st.warning(
            f"所选月份有 {missing:,} 件进出库记录缺少成本，"
            "本月金额暂未完整。请打开“成本维护”，填写对应入库批次的单位成本。"
        )
    if inventory_value["missing_cost_quantity"]:
        st.warning(
            f"当前库存有 {inventory_value['missing_cost_quantity']:,} 件缺少成本，"
            "库存总成本暂未包含这些商品。请打开“成本维护”，"
            "优先处理标记为“缺成本”的批次。"
        )

    daily = _build_two_week_daily_amounts(recent_finance_df, report_date)
    st.subheader("近14天每日进出库金额")
    two_week_inbound = float(daily["入库金额"].sum())
    two_week_outbound = float(daily["出库成本"].sum())
    recent_columns = st.columns(3)
    recent_columns[0].metric("近14天入库", f"${two_week_inbound:,.2f}")
    recent_columns[1].metric("近14天出库", f"${two_week_outbound:,.2f}")
    recent_columns[2].metric(
        "近14天净变化", f"${two_week_inbound - two_week_outbound:,.2f}"
    )
    amount_chart = daily.set_index("日期")[["入库金额", "出库成本"]]
    st.bar_chart(
        amount_chart,
        color=["#167D6D", "#D95D39"],
        height=320,
    )
    st.dataframe(
        daily.sort_values("日期排序", ascending=False).drop(
            columns=["日期排序"]
        ),
        width="stretch",
        hide_index=True,
        column_config=_financial_column_config(daily.columns),
    )


def _build_two_week_daily_amounts(finance_df, report_date):
    date_range = pd.date_range(
        report_date - timedelta(days=13), report_date, freq="D"
    )
    daily = build_daily_summary(finance_df)
    if daily.empty:
        amounts = pd.DataFrame(
            0.0, index=date_range, columns=["入库金额", "出库成本"]
        )
    else:
        amounts = daily.copy()
        amounts["日期"] = pd.to_datetime(amounts["日期"])
        amounts = (
            amounts.set_index("日期")[["入库金额", "出库成本"]]
            .reindex(date_range, fill_value=0)
        )
    amounts.index.name = "日期排序"
    result = amounts.reset_index()
    result.insert(0, "日期", result["日期排序"].dt.strftime("%m/%d"))
    return result[["日期", "日期排序", "入库金额", "出库成本"]]



def _render_department_summary(finance_df):
    summary_rows = _render_inventory_filters(
        finance_df, key="finance_summary_filters"
    )
    summary = build_department_summary(summary_rows)
    st.dataframe(
        summary,
        width="stretch",
        hide_index=True,
        column_config=_financial_column_config(summary.columns),
    )


def _render_inbound_batches(finance_df):
    batch_rows = _render_inventory_filters(
        finance_df, key="finance_batch_filters"
    )
    render_inbound_batch_browser(batch_rows)


def _render_cost_maintenance(supabase, finance_df, missing_cost_df):
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


def _render_cost_detail(finance_df):
    detail_rows = _render_inventory_filters(
        finance_df, key="finance_detail_filters"
    )
    detail = detail_rows.rename(columns={
        "date": "日期",
        "direction": "类型",
        "department": "部门",
        "category": "品类",
        "brand": "品牌",
        "material": "材质",
        "color": "颜色",
        "size": "尺码/型号",
        "quantity": "数量",
        "unit_cost": "单位成本",
        "amount": "金额",
        "source_type": "成本来源",
    })
    visible = [
        "日期", "类型", "部门", "品类", "品牌", "材质",
        "颜色", "尺码/型号", "数量", "单位成本", "金额", "成本来源",
    ]
    st.dataframe(
        detail[visible] if not detail.empty else detail,
        width="stretch",
        hide_index=True,
        column_config=_financial_column_config(visible),
    )


def _render_inventory_filters(finance_df, *, key):
    if finance_df.empty:
        return finance_df
    st.markdown("#### 筛选成本范围")
    dimensions = finance_df[[
        "department", "category", "brand", "material", "color", "size",
    ]].drop_duplicates()
    department, category, brands, materials, colors, sizes = (
        render_inventory_dimension_filters(
            dimensions, key=key,
            allow_all_departments=True,
        )
    )
    filtered = filter_inventory_rows(
        finance_df, category, brands, materials, colors, sizes
    )
    if department:
        filtered = filtered[filtered["department"] == department]
    return filtered.reset_index(drop=True)

def _render_container_report(container_df, month):
    st.caption(
        f"{month.year}年{month.month}月 · 按预计到货日期统计，"
        "不与库存入库金额合并"
    )
    summary = build_container_summary(container_df)
    quantity = int(summary["数量"].sum()) if not summary.empty else 0
    amount = float(summary["采购金额"].sum()) if not summary.empty else 0
    missing = int(summary["缺成本件数"].sum()) if not summary.empty else 0

    columns = st.columns(3)
    columns[0].metric("货柜数", f"{len(summary):,}")
    columns[1].metric("预计到货数量", f"{quantity:,}")
    columns[2].metric("采购金额", f"${amount:,.2f}")
    if missing:
        st.warning(f"有 {missing:,} 件货柜商品未填写成本。")

    if summary.empty:
        st.info("本月没有预计到货的货柜")
        return
    st.dataframe(
        summary,
        width="stretch",
        hide_index=True,
        column_config=_financial_column_config(summary.columns),
    )


def _financial_column_config(columns):
    config = {}
    for column in columns:
        if column in {"入库金额", "出库成本", "成本净增加", "采购金额", "金额"}:
            config[column] = st.column_config.NumberColumn(format="$%.2f")
        elif column == "单位成本":
            config[column] = st.column_config.NumberColumn(format="$%.4f")
        elif column in {
            "入库数量", "出库数量", "库存数量净变动", "数量", "缺成本件数",
        }:
            config[column] = st.column_config.NumberColumn(format="%d")
    return config
