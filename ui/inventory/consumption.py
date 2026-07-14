from datetime import timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from db.inventory import SIZE_COLUMNS, build_color_inventory_table
from db.inventory.consumption import (
    DEFAULT_ORDER_QUANTITY,
    build_consumption_model_table,
    load_consumption_model,
    scale_consumption_model,
)
from db.inventory.consumption_alerts import build_inventory_consumption_alerts
from ui.inventory.i18n import t


def render_consumption_planning_inputs(category):
    if category != "黑白短袖":
        return DEFAULT_ORDER_QUANTITY, None, 0

    today = st.session_state.get("inventory_today")
    if today is None:
        from datetime import datetime

        today = datetime.now(ZoneInfo("America/New_York")).date()

    col1, col2, col3 = st.columns(3)
    order_quantity = col1.number_input(
        t("Haloo 订单量"),
        min_value=1000,
        max_value=100000,
        value=DEFAULT_ORDER_QUANTITY,
        step=1000,
        key="haloo_consumption_order_quantity",
    )
    arrival_date = col2.date_input(
        t("预计到货日期"),
        value=today + timedelta(days=10),
        min_value=today,
        key="inventory_arrival_date",
    )
    buffer_days = col3.number_input(
        t("容错天数"),
        min_value=0,
        max_value=30,
        value=3,
        step=1,
        key="inventory_buffer_days",
    )
    return order_quantity, arrival_date, buffer_days


def render_black_white_color_summary(
    category,
    inventory_df,
):
    if category != "黑白短袖":
        return

    st.subheader(t("黑白短袖颜色库存汇总"))
    color_df = build_color_inventory_table(inventory_df)
    if color_df.empty:
        st.info(t("暂无黑白短袖库存数据"))
        return

    st.dataframe(
        color_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "颜色": st.column_config.TextColumn(t("颜色")),
            "总库存": st.column_config.NumberColumn(t("总库存"), format="%d"),
            **{size: st.column_config.NumberColumn(size, format="%d") for size in SIZE_COLUMNS},
        },
    )


def render_reorder_forecast(
    supabase,
    category,
    inventory_df,
    order_quantity,
    arrival_date,
    buffer_days,
    inventory_date,
):
    if category != "黑白短袖":
        return DEFAULT_ORDER_QUANTITY

    st.subheader(t("点货预测表"))
    color_df = build_color_inventory_table(inventory_df)
    if color_df.empty:
        st.info(t("暂无可预测库存数据"))
        return order_quantity

    try:
        model_df = load_consumption_model(supabase, category)
        model_df = scale_consumption_model(model_df, order_quantity)
        today = st.session_state.get("inventory_today")
        days_to_arrival = max((arrival_date - today).days, 0) if arrival_date and today else 0
        coverage_days = days_to_arrival + int(buffer_days)
        forecast_df = build_inventory_consumption_alerts(
            color_df,
            model_df,
            coverage_days=coverage_days,
            inventory_date=inventory_date,
            current_date=today,
        )
    except Exception as e:
        st.info(t("暂无点货预测数据"))
        st.caption(str(e))
        return order_quantity

    forecast_columns = [
        "颜色",
        "库存基准日期",
        "当前日期",
        "最低剩余天数",
        "预计最早耗尽日期",
        "低于14天尺码",
        "到货前需覆盖天数",
        "到货前缺口总数",
        "到货前缺口尺码",
    ]
    forecast_df = forecast_df[[column for column in forecast_columns if column in forecast_df.columns]]

    display_df = forecast_df.style.apply(
        lambda row: [
            "background-color: #ffe0e0; color: #8a0000; font-weight: 700;"
            if is_low_consumption_alert(row.get("最低剩余天数")) and column in ["最低剩余天数", "低于14天尺码"]
            else "background-color: #fff1cc; color: #7a4a00; font-weight: 700;"
            if has_arrival_shortage(row.get("到货前缺口总数")) and column in ["到货前缺口总数", "到货前缺口尺码"]
            else ""
            for column in row.index
        ],
        axis=1,
    )

    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "颜色": st.column_config.TextColumn(t("颜色")),
            "最低剩余天数": st.column_config.NumberColumn(t("最低剩余天数"), format="%d"),
            "库存基准日期": st.column_config.DateColumn(t("库存基准日期"), format="YYYY-MM-DD"),
            "当前日期": st.column_config.DateColumn(t("当前日期"), format="YYYY-MM-DD"),
            "预计最早耗尽日期": st.column_config.DateColumn(
                t("预计最早耗尽日期"), format="YYYY-MM-DD"
            ),
            "低于14天尺码": st.column_config.TextColumn(t("低于14天尺码")),
            "到货前需覆盖天数": st.column_config.NumberColumn(t("到货前需覆盖天数"), format="%d"),
            "到货前缺口总数": st.column_config.NumberColumn(t("到货前缺口总数"), format="%d"),
            "到货前缺口尺码": st.column_config.TextColumn(t("到货前缺口尺码")),
        },
    )
    return order_quantity


def is_low_consumption_alert(days):
    try:
        return float(days) < 14
    except (TypeError, ValueError):
        return False


def has_arrival_shortage(quantity):
    try:
        return float(quantity) > 0
    except (TypeError, ValueError):
        return False


def render_consumption_model(supabase, category, order_quantity):
    if category != "黑白短袖":
        return

    st.subheader(f"Haloo {order_quantity:,}{t('单消耗模型')}")
    try:
        model_df = load_consumption_model(supabase, category)
        model_df = scale_consumption_model(model_df, order_quantity)
    except Exception as e:
        st.info(t("请先运行消耗模型 SQL"))
        st.caption(str(e))
        return

    display_df = build_consumption_model_table(model_df)
    if display_df.empty:
        st.info(t("暂无消耗模型数据"))
        return

    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            **{size: st.column_config.NumberColumn(size, format="%d") for size in SIZE_COLUMNS},
        },
    )
