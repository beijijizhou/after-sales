"""Finance report renderers and shared inventory-scope filtering."""

from datetime import timedelta

import pandas as pd
import streamlit as st

from db.finance import (
    build_container_summary,
    build_daily_summary,
    build_department_summary,
    build_finance_overview,
    build_inventory_value_overview,
)
from ui.inventory.shared import filter_inventory_rows, render_inventory_dimension_filters
from utils.sku_sorting import sort_sku_rows


def render_inventory_report(finance_df, recent_df, value_df, month, report_date):
    st.caption(f"{month.year}年{month.month}月 · 金额为库存成本，不是销售额")
    overview = build_finance_overview(finance_df)
    inventory_value = build_inventory_value_overview(value_df)
    columns = st.columns(3)
    columns[0].metric("当前库存成本", f"${inventory_value['inventory_value']:,.2f}")
    columns[1].metric("本月入库金额", f"${overview['inbound_amount']:,.2f}")
    columns[2].metric("本月出库成本", f"${overview['outbound_amount']:,.2f}")
    missing = overview["missing_inbound_quantity"] + overview["missing_outbound_quantity"]
    if missing:
        st.warning(f"所选月份有 {missing:,} 个库存单位缺少成本，请到“成本维护”填写。")
    if inventory_value["missing_cost_quantity"]:
        st.warning(
            f"当前库存有 {inventory_value['missing_cost_quantity']:,} 个单位缺少成本。"
        )
    daily = build_two_week_daily_amounts(recent_df, report_date)
    st.subheader("近14天每日进出库金额")
    inbound, outbound = float(daily["入库金额"].sum()), float(daily["出库成本"].sum())
    metrics = st.columns(3)
    metrics[0].metric("近14天入库", f"${inbound:,.2f}")
    metrics[1].metric("近14天出库", f"${outbound:,.2f}")
    metrics[2].metric("近14天净变化", f"${inbound - outbound:,.2f}")
    st.bar_chart(
        daily.set_index("日期")[["入库金额", "出库成本"]],
        color=["#167D6D", "#D95D39"], height=320,
    )
    st.dataframe(
        daily.sort_values("日期排序", ascending=False).drop(columns=["日期排序"]),
        width="stretch", hide_index=True,
        column_config=financial_column_config(daily.columns),
    )


def build_two_week_daily_amounts(finance_df, report_date):
    dates = pd.date_range(report_date - timedelta(days=13), report_date, freq="D")
    daily = build_daily_summary(finance_df)
    if daily.empty:
        amounts = pd.DataFrame(0.0, index=dates, columns=["入库金额", "出库成本"])
    else:
        daily["日期"] = pd.to_datetime(daily["日期"])
        amounts = daily.set_index("日期")[["入库金额", "出库成本"]].reindex(
            dates, fill_value=0
        )
    amounts.index.name = "日期排序"
    result = amounts.reset_index()
    result.insert(0, "日期", result["日期排序"].dt.strftime("%m/%d"))
    return result[["日期", "日期排序", "入库金额", "出库成本"]]


def render_department_summary(finance_df):
    summary = build_department_summary(
        render_inventory_filters(finance_df, key="finance_summary_filters")
    )
    st.dataframe(
        summary, width="stretch", hide_index=True,
        column_config=financial_column_config(summary.columns),
    )


def render_cost_detail(finance_df):
    detail = render_inventory_filters(
        finance_df, key="finance_detail_filters"
    ).rename(columns={
        "date": "日期", "direction": "类型", "department": "部门",
        "category": "品类", "brand": "品牌", "material": "材质",
        "color": "颜色", "size": "尺码/型号", "quantity": "数量",
        "unit_cost": "单位成本", "amount": "金额", "source_type": "成本来源",
    })
    visible = [
        "日期", "类型", "部门", "品类", "品牌", "材质", "颜色",
        "尺码/型号", "数量", "单位成本", "金额", "成本来源",
    ]
    detail = sort_sku_rows(
        detail, leading=["日期", "类型"], leading_ascending=[False, True]
    )
    st.dataframe(
        detail[visible] if not detail.empty else detail,
        width="stretch", hide_index=True,
        column_config=financial_column_config(visible),
    )


def render_inventory_filters(finance_df, *, key):
    if finance_df.empty:
        return finance_df
    st.markdown("#### 筛选成本范围")
    dimensions = finance_df[[
        "department", "category", "brand", "material", "color", "size",
    ]].drop_duplicates()
    department, category, brands, materials, colors, sizes = (
        render_inventory_dimension_filters(
            dimensions, key=key, allow_all_departments=True
        )
    )
    filtered = filter_inventory_rows(
        finance_df, category, brands, materials, colors, sizes
    )
    if department:
        filtered = filtered[filtered["department"] == department]
    return filtered.reset_index(drop=True)


def render_container_report(container_df, month):
    st.caption(f"{month.year}年{month.month}月 · 按预计到货日期统计")
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
        summary, width="stretch", hide_index=True,
        column_config=financial_column_config(summary.columns),
    )


def financial_column_config(columns):
    config = {}
    for column in columns:
        if column in {"入库金额", "出库成本", "成本净增加", "采购金额", "金额"}:
            config[column] = st.column_config.NumberColumn(format="$%.2f")
        elif column == "单位成本":
            config[column] = st.column_config.NumberColumn(format="$%.4f")
        elif column in {"入库数量", "出库数量", "库存数量净变动", "数量", "缺成本件数"}:
            config[column] = st.column_config.NumberColumn(format="%d")
    return config
