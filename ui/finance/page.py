from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.finance import (
    build_container_summary,
    build_daily_summary,
    build_department_summary,
    build_finance_overview,
    load_container_finance_month,
    load_inventory_finance_month,
)


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_finance_page(supabase):
    st.title("财务")
    month = _render_month_selector()
    start_date, end_date = _month_range(month)

    with st.spinner("正在汇总月度财务数据..."):
        finance_df = load_inventory_finance_month(
            supabase, start_date, end_date
        )
        container_df = load_container_finance_month(
            supabase, start_date, end_date
        )

    inventory_tab, container_tab = st.tabs([
        "商品库存月报", "货柜采购",
    ])
    with inventory_tab:
        _render_inventory_report(finance_df, month)
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


def _render_inventory_report(finance_df, month):
    st.caption(
        f"{month.year}年{month.month}月 · 金额为库存成本，不是销售额"
    )
    overview = build_finance_overview(finance_df)
    columns = st.columns(4)
    columns[0].metric("入库数量", f"{overview['inbound_quantity']:,.0f}")
    columns[1].metric("入库金额", f"${overview['inbound_amount']:,.2f}")
    columns[2].metric("出库数量", f"{overview['outbound_quantity']:,.0f}")
    columns[3].metric("出库成本", f"${overview['outbound_amount']:,.2f}")

    missing = (
        overview["missing_inbound_quantity"]
        + overview["missing_outbound_quantity"]
    )
    if missing:
        st.warning(
            f"有 {missing:,} 件尚未填写成本，金额汇总暂未包含这些件数。"
        )

    summary = build_department_summary(finance_df)
    st.subheader("部门及品类汇总")
    st.dataframe(
        summary,
        width="stretch",
        hide_index=True,
        column_config=_financial_column_config(summary.columns),
    )

    daily = build_daily_summary(finance_df)
    st.subheader("每日出入库")
    if daily.empty:
        st.info("本月暂无库存出入库记录")
    else:
        quantity_chart = daily.set_index("日期")[["入库数量", "出库数量"]]
        st.bar_chart(
            quantity_chart,
            color=["#167D6D", "#D95D39"],
            height=320,
        )
        st.dataframe(
            daily,
            width="stretch",
            hide_index=True,
            column_config=_financial_column_config(daily.columns),
        )

    with st.expander("查看成本明细"):
        detail = finance_df.rename(columns={
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
