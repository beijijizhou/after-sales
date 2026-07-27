from datetime import timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from automation.production_period import load_period_production_model
from db.inventory import (
    SIZE_COLUMNS,
    build_color_inventory_table,
)
from db.inventory.planning.consumption import (
    DEFAULT_ORDER_QUANTITY,
    load_consumption_model,
    scale_consumption_model,
)
from db.inventory.planning.consumption_alerts import build_inventory_consumption_alerts
from db.inventory.planning.consumption_comparison import (
    build_period_model_comparison,
    build_prioritized_consumption_model,
)
from db.inventory.planning.demand_anomaly import (
    build_demand_anomaly_table,
    load_daily_outbound_history,
)
from ui.inventory.planning.anomaly import render_demand_anomaly_monitor
from ui.inventory.planning.forecast_controls import (
    render_forecast_calculation,
    render_forecast_model_controls,
)
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


def render_reorder_forecast(
    supabase,
    department,
    category,
    inventory_df,
    order_quantity,
    arrival_date,
    buffer_days,
    inventory_date,
    visible_sizes=None,
):
    if category != "黑白短袖":
        return DEFAULT_ORDER_QUANTITY

    color_df = build_color_inventory_table(inventory_df)
    if color_df.empty:
        st.info(t("暂无可预测库存数据"))
        return order_quantity

    source_weights = render_forecast_model_controls()
    try:
        model_df = load_consumption_model(supabase, category)
        model_df = scale_consumption_model(model_df, order_quantity)
        if visible_sizes:
            model_df = model_df[model_df["size"].isin(visible_sizes)]
        today = st.session_state.get("inventory_today")
        anomaly_error_message = None
        try:
            outbound_df = load_daily_outbound_history(
                supabase, department, category, today
            )
            if visible_sizes:
                outbound_df = outbound_df[
                    outbound_df["尺码"].isin(visible_sizes)
                ]
            anomaly_df = build_demand_anomaly_table(
                model_df, outbound_df, inventory_df
            )
        except Exception as anomaly_error:
            anomaly_df = pd.DataFrame()
            outbound_df = pd.DataFrame()
            anomaly_error_message = str(anomaly_error)
        production = load_period_production_model(
            today, 14, category
        )
        comparison_df = build_period_model_comparison(
            model_df,
            outbound_df,
            production.data,
            today,
            days=14,
            platform_days=production.effective_days,
        )
        forecast_model_df = build_prioritized_consumption_model(
            comparison_df, source_weights
        )
        days_to_arrival = max((arrival_date - today).days, 0) if arrival_date and today else 0
        coverage_days = days_to_arrival + int(buffer_days)
        forecast_df = build_inventory_consumption_alerts(
            color_df,
            forecast_model_df,
            coverage_days=coverage_days,
            inventory_date=inventory_date,
            current_date=today,
            sizes=visible_sizes,
        )
        materials = sorted({
            str(value).strip()
            for value in inventory_df.get(
                "材质", pd.Series(dtype=str)
            ).dropna()
            if str(value).strip()
        })
        forecast_df["材质范围"] = "、".join(materials) or t("未填写")
        forecast_df["日耗依据"] = t(
            "优先级综合模型"
        )
    except Exception as e:
        st.info(t("暂无点货预测数据"))
        st.caption(str(e))
        return order_quantity

    st.subheader(t("点货预测表"))
    st.caption(t("库存按当前筛选材质合计，并合并同材质下的全部所选品牌。"))
    st.caption(t(
        "缺失数据来源时，其占比会自动按其他可用来源重新分配。"
    ))
    render_reorder_forecast_table(forecast_df)
    render_forecast_calculation(
        comparison_df,
        forecast_model_df,
        production.effective_days,
        production.start_date,
        production.end_date,
    )
    if anomaly_error_message:
        st.warning(f"{t('异常消耗加载失败')}: {anomaly_error_message}")
    st.caption(t("异常出库仅用于提醒，不直接替代点货预测日耗。"))
    render_demand_anomaly_monitor(anomaly_df)
    return order_quantity
