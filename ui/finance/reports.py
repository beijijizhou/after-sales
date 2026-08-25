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
    st.markdown("#### SKU 筛选")
    dimensions = build_finance_scope_dimensions(finance_df, value_df)
    scope = render_inventory_dimension_filters(
        dimensions, key="finance_monthly_scope", allow_all_departments=True
    )
    finance_df = filter_finance_scope(finance_df, scope)
    recent_df = filter_finance_scope(recent_df, scope)
    value_df = filter_finance_scope(value_df, scope)
    overview = build_finance_overview(finance_df)
    inventory_value = build_inventory_value_overview(value_df)
    columns = st.columns(3)
    columns[0].metric("当前库存成本", f"${inventory_value['inventory_value']:,.2f}")
    columns[1].metric("本月入库金额", f"${overview['inbound_amount']:,.2f}")
    columns[2].metric("本月出库成本", f"${overview['outbound_amount']:,.2f}")
    missing = overview["missing_inbound_quantity"] + overview["missing_outbound_quantity"]
    if missing:
        st.warning(
            f"所选月份有 {missing:,} 个库存单位缺少成本，"
            "请到“库存 → 库存成本”填写。"
        )
    if inventory_value["missing_cost_quantity"]:
        st.warning(
            f"当前库存有 {inventory_value['missing_cost_quantity']:,} 个单位缺少成本。"
        )
        render_missing_cost_navigation(
            value_df, key="finance_monthly_missing_cost"
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
    return filter_finance_scope(
        finance_df,
        (department, category, brands, materials, colors, sizes),
    )


def build_finance_scope_dimensions(*frames):
    """Build one selector scope shared by stock value and monthly movements."""
    columns = ["department", "category", "brand", "material", "color", "size"]
    parts = []
    for frame in frames:
        data = pd.DataFrame(frame).copy()
        if data.empty:
            continue
        for column in columns:
            if column not in data:
                data[column] = ""
        parts.append(data[columns])
    if not parts:
        return pd.DataFrame(columns=columns)
    return pd.concat(parts, ignore_index=True).drop_duplicates().reset_index(
        drop=True
    )


def filter_finance_scope(rows, scope):
    """Apply one inventory dimension selection to any finance data frame."""
    data = pd.DataFrame(rows).copy()
    if data.empty:
        return data
    department, category, brands, materials, colors, sizes = scope
    filtered = filter_inventory_rows(
        data, category, brands, materials, colors, sizes
    )
    if department and "department" in filtered:
        filtered = filtered[filtered["department"] == department]
    return filtered.reset_index(drop=True)


def build_missing_cost_scope_summary(value_df):
    data = pd.DataFrame(value_df).copy()
    columns = ["部门", "品类", "单位", "缺成本数量"]
    if data.empty or "missing_cost_quantity" not in data:
        return pd.DataFrame(columns=columns)
    data["missing_cost_quantity"] = pd.to_numeric(
        data["missing_cost_quantity"], errors="coerce"
    ).fillna(0)
    data = data[data["missing_cost_quantity"] > 0]
    if data.empty:
        return pd.DataFrame(columns=columns)
    for column in ["department", "category"]:
        if column not in data:
            data[column] = ""
        data[column] = data[column].fillna("").astype(str)
    if "quantity_unit" not in data:
        data["quantity_unit"] = "件"
    data["quantity_unit"] = data["quantity_unit"].fillna("").astype(str)
    data.loc[data["quantity_unit"].str.strip() == "", "quantity_unit"] = "件"
    return (
        data.groupby(
            ["department", "category", "quantity_unit"], as_index=False
        )
        .agg(missing_cost_quantity=("missing_cost_quantity", "sum"))
        .rename(columns={
            "department": "部门", "category": "品类",
            "quantity_unit": "单位",
            "missing_cost_quantity": "缺成本数量",
        })[columns]
        .sort_values("缺成本数量", ascending=False, kind="stable")
        .reset_index(drop=True)
    )


def render_missing_cost_navigation(value_df, *, key):
    summary = build_missing_cost_scope_summary(value_df)
    if summary.empty:
        return
    st.markdown("#### 缺成本位置")
    st.dataframe(
        summary, hide_index=True, width="stretch",
        column_config={
            "缺成本数量": st.column_config.NumberColumn(format="%d"),
        },
    )
    options = list(range(len(summary)))
    labels = {
        index: (
            f"{row['部门']}｜{row['品类'] or '全部品类'}｜"
            f"{int(row['缺成本数量']):,} {row['单位']}"
        )
        for index, row in summary.iterrows()
    }
    selected = st.selectbox(
        "选择需要处理的范围", options,
        format_func=lambda value: labels[value], key=f"{key}_scope",
    )
    if not st.button(
        "前往库存成本处理", type="primary", width="stretch",
        key=f"{key}_open_inventory_cost",
    ):
        return
    target = summary.iloc[int(selected)]
    _open_inventory_cost_scope(target["部门"], target["品类"])


def _open_inventory_cost_scope(department, category):
    from ui.inventory.i18n import t
    from ui.inventory.page_tabs import inventory_tab_state_key

    department = str(department or "").strip()
    category = str(category or "").strip()
    st.session_state["inventory_global_department"] = department
    st.session_state[f"inventory_global_{department}_category"] = category
    st.session_state[inventory_tab_state_key(department, category)] = t(
        "库存成本"
    )
    st.switch_page("pages/4_库存.py")


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
