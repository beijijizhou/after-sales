from datetime import timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.inventory import (
    SIZE_COLUMNS,
    build_color_inventory_table,
)
from db.inventory.planning.consumption import (
    DEFAULT_ORDER_QUANTITY,
)
from db.inventory.planning.consumption_alerts import build_inventory_consumption_alerts
from db.inventory.planning.consumption_comparison import (
    build_period_model_comparison,
)
from db.inventory.planning.demand_anomaly import (
    build_demand_anomaly_table,
)
from db.inventory.planning.outbound_consumption import (
    apparel_forecast_model,
    load_outbound_consumption,
)
from ui.inventory.planning.anomaly import render_demand_anomaly_monitor
from ui.inventory.planning.forecast_controls import (
    render_forecast_calculation,
    render_order_model_breakdown,
    render_forecast_usage_adjustment,
)
from ui.inventory.planning.forecast_table import render_reorder_forecast_table
from ui.inventory.i18n import t
from ui.planning import (
    render_consumption_window_input,
    render_target_days_input,
)


def render_consumption_planning_inputs(category):
    today = st.session_state.get("inventory_today")
    if today is None:
        from datetime import datetime

        today = datetime.now(ZoneInfo("America/New_York")).date()

    if category not in {"黑白短袖", "彩色短袖"}:
        target_days = render_target_days_input(
            st,
            key=f"inventory_target_stock_days_{category or 'all'}",
            default_days=55,
            step=5,
        )
        return DEFAULT_ORDER_QUANTITY, None, 0, target_days

    columns = st.columns(3)
    order_quantity = DEFAULT_ORDER_QUANTITY
    date_column, buffer_column, target_column = columns
    arrival_date = date_column.date_input(
        t("预计到货日期"),
        value=today + timedelta(days=10),
        min_value=today,
        key=f"inventory_arrival_date_{category}",
    )
    buffer_days = buffer_column.number_input(
        t("容错天数"),
        min_value=0,
        max_value=30,
        value=3,
        step=1,
        key=f"inventory_buffer_days_{category}",
    )
    target_days = render_target_days_input(
        target_column,
        key=f"inventory_target_stock_days_{category}",
        default_days=55,
        step=5,
    )
    return order_quantity, arrival_date, buffer_days, target_days


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
    target_days=55,
    source_weights=None,
    calculation_container=None,
    anomaly_container=None,
    brands=None,
    materials=None,
    colors=None,
    sizes=None,
):
    if category not in {"黑白短袖", "彩色短袖"}:
        return pd.DataFrame()

    color_df = build_color_inventory_table(inventory_df)
    if color_df.empty:
        st.info(t("暂无可预测库存数据"))
        return pd.DataFrame()

    lookback_days = render_consumption_window_input(
        st,
        key=f"inventory_consumption_lookback_{department}_{category}",
    )

    try:
        order_breakdown_container = None
        today = st.session_state.get("inventory_today")
        if today is None:
            from datetime import datetime

            today = datetime.now(ZoneInfo("America/New_York")).date()
        consumption = load_outbound_consumption(
            supabase, department, category, today,
            window_days=lookback_days,
            brands=brands,
            materials=materials,
            colors=colors,
            sizes=sizes,
        )
        outbound_df = consumption.history
        if visible_sizes:
            outbound_df = outbound_df[
                outbound_df["尺码"].isin(visible_sizes)
            ]
        model_df = apparel_forecast_model(consumption.usage)
        if visible_sizes:
            model_df = model_df[model_df["size"].isin(visible_sizes)]
        if category == "黑白短袖":
            order_breakdown_container = st.container()
        anomaly_error_message = None
        if category == "黑白短袖":
            try:
                anomaly_df = build_demand_anomaly_table(
                    model_df, outbound_df, inventory_df, today
                )
            except Exception as anomaly_error:
                anomaly_df = pd.DataFrame()
                outbound_df = pd.DataFrame()
                anomaly_error_message = str(anomaly_error)
            comparison_df = build_period_model_comparison(
                model_df, outbound_df, pd.DataFrame(), today,
                days=lookback_days,
            )
            forecast_model_df = model_df.copy()
        else:
            anomaly_df = pd.DataFrame()
            comparison_df = pd.DataFrame()
            forecast_model_df = model_df.copy()
        if visible_sizes:
            forecast_model_df = forecast_model_df[
                forecast_model_df["size"].isin(visible_sizes)
            ]
        if forecast_model_df.empty:
            raise ValueError("最近30天暂无可用于点货预测的仓库人工出库数据")
        forecast_base_model_df = forecast_model_df.copy()
        forecast_model_df, _ = render_forecast_usage_adjustment(
            forecast_model_df,
            0,
            lookback_days,
            category,
            pd.DataFrame(),
            outbound_df,
            today,
            0,
        )
        if order_breakdown_container is not None:
            with order_breakdown_container:
                render_order_model_breakdown(
                    forecast_model_df,
                    order_quantity,
                    base_model_df=forecast_base_model_df,
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
            target_days=target_days,
        )
        materials = sorted({
            str(value).strip()
            for value in inventory_df.get(
                "材质", pd.Series(dtype=str)
            ).dropna()
            if str(value).strip()
        })
        forecast_df["材质范围"] = "、".join(materials) or t("未填写")
        forecast_df["日耗依据"] = (
            f"最近{lookback_days}天仓库人工出库（可自定义）"
        )
    except Exception as e:
        st.info(t("暂无点货预测数据"))
        st.caption(str(e))
        return pd.DataFrame()

    st.subheader(t("点货预测表"))
    st.caption(
        "当前计算严格沿用页面顶部的品牌、材质、颜色和尺码筛选；"
        f"材质范围：{'、'.join(materials) or t('未填写')}。"
        "订单源数据没有材质字段，因此不把订单数强行归到 CVC、160g 或 180g。"
    )
    st.caption(
        f"本页只计算{category}：仓库人工登记的每日实际出库是正式消耗基准；"
        "平台生产和旧订单模型只作独立参考，不参与默认预测。"
    )
    st.caption("当前品类的自定义日耗会同步更新其建议点货量和货柜联动。")
    render_reorder_forecast_table(forecast_df)
    if category == "黑白短袖":
        calculation_target = (
            calculation_container
            if calculation_container is not None else st.container()
        )
        with calculation_target:
            render_forecast_calculation(
                comparison_df,
                forecast_model_df,
                0,
                None,
                None,
            )
        anomaly_target = (
            anomaly_container
            if anomaly_container is not None else st.container()
        )
        with anomaly_target:
            if anomaly_error_message:
                st.warning(f"{t('异常消耗加载失败')}: {anomaly_error_message}")
            st.caption(t("异常出库仅用于提醒，不直接替代点货预测日耗。"))
            render_demand_anomaly_monitor(anomaly_df)
    return forecast_model_df
