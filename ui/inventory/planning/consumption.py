from datetime import timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS, build_color_inventory_table
from db.inventory.planning.consumption import (
    DEFAULT_ORDER_QUANTITY,
    build_consumption_model_table,
    load_consumption_model,
    scale_consumption_model,
)
from db.inventory.planning.consumption_alerts import build_inventory_consumption_alerts
from db.inventory.planning.demand_anomaly import (
    apply_risk_consumption,
    build_demand_anomaly_table,
    load_daily_outbound_history,
)
from ui.inventory.planning.anomaly import render_demand_anomaly_monitor
from ui.inventory.planning.comparison import render_model_comparison
from ui.inventory.planning.forecast_table import render_reorder_forecast_table
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
        width="stretch",
        column_config={
            "颜色": st.column_config.TextColumn(t("颜色")),
            "总库存": st.column_config.NumberColumn(t("总库存"), format="%d"),
            **{size: st.column_config.NumberColumn(size, format="%d") for size in SIZE_COLUMNS},
        },
    )


def render_reorder_forecast(
    supabase,
    department,
    category,
    inventory_df,
    order_quantity,
    arrival_date,
    buffer_days,
    inventory_date,
):
    if category != "黑白短袖":
        return DEFAULT_ORDER_QUANTITY

    color_df = build_color_inventory_table(inventory_df)
    if color_df.empty:
        st.info(t("暂无可预测库存数据"))
        return order_quantity

    try:
        model_df = load_consumption_model(supabase, category)
        model_df = scale_consumption_model(model_df, order_quantity)
        today = st.session_state.get("inventory_today")
        anomaly_error_message = None
        try:
            outbound_df = load_daily_outbound_history(
                supabase, department, category, today
            )
            anomaly_df = build_demand_anomaly_table(
                model_df, outbound_df, inventory_df
            )
        except Exception as anomaly_error:
            anomaly_df = pd.DataFrame()
            outbound_df = pd.DataFrame()
            anomaly_error_message = str(anomaly_error)
        risk_model_df = apply_risk_consumption(model_df, anomaly_df)
        days_to_arrival = max((arrival_date - today).days, 0) if arrival_date and today else 0
        coverage_days = days_to_arrival + int(buffer_days)
        forecast_df = build_inventory_consumption_alerts(
            color_df,
            risk_model_df,
            coverage_days=coverage_days,
            inventory_date=inventory_date,
            current_date=today,
        )
    except Exception as e:
        st.info(t("暂无点货预测数据"))
        st.caption(str(e))
        return order_quantity

    st.subheader(t("点货预测表"))
    render_reorder_forecast_table(forecast_df)
    if anomaly_error_message:
        st.warning(f"{t('异常消耗加载失败')}: {anomaly_error_message}")
    render_demand_anomaly_monitor(anomaly_df)
    render_model_comparison(model_df, outbound_df, today)
    return order_quantity


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
        width="stretch",
        column_config={
            **{size: st.column_config.NumberColumn(size, format="%d") for size in SIZE_COLUMNS},
        },
    )
