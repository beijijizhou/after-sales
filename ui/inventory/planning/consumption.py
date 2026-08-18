from datetime import timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from automation.production_period import (
    DEFAULT_RECENT_DAYS,
    load_recent_production_model,
)
from automation.production import DTF_PRODUCTION_PLATFORMS
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
    render_forecast_usage_adjustment,
)
from ui.inventory.planning.forecast_table import render_reorder_forecast_table
from ui.inventory.i18n import t
from ui.planning import render_target_days_input


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

    columns = st.columns(4 if category == "黑白短袖" else 3)
    if category == "黑白短袖":
        order_quantity = columns[0].number_input(
            t("Haloo 订单量"),
            min_value=1000,
            max_value=100000,
            value=DEFAULT_ORDER_QUANTITY,
            step=1000,
            key="haloo_consumption_order_quantity",
        )
        date_column, buffer_column, target_column = columns[1:]
    else:
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
):
    if category not in {"黑白短袖", "彩色短袖"}:
        return pd.DataFrame()

    color_df = build_color_inventory_table(inventory_df)
    if color_df.empty:
        st.info(t("暂无可预测库存数据"))
        return pd.DataFrame()

    try:
        today = st.session_state.get("inventory_today")
        if today is None:
            from datetime import datetime

            today = datetime.now(ZoneInfo("America/New_York")).date()
        production = load_recent_production_model(
            today, DEFAULT_RECENT_DAYS, category, supabase
        )
        if category == "黑白短袖":
            source_weights = render_forecast_model_controls(order_quantity)
            model_df = load_consumption_model(supabase, category)
            model_df = scale_consumption_model(model_df, order_quantity)
            if visible_sizes:
                model_df = model_df[model_df["size"].isin(visible_sizes)]
        else:
            source_weights = None
            model_df = pd.DataFrame()
        anomaly_error_message = None
        if category == "黑白短袖":
            try:
                outbound_df = load_daily_outbound_history(
                    supabase, department, category, today
                )
                if visible_sizes:
                    outbound_df = outbound_df[
                        outbound_df["尺码"].isin(visible_sizes)
                    ]
                anomaly_df = build_demand_anomaly_table(
                    model_df, outbound_df, inventory_df, today
                )
            except Exception as anomaly_error:
                anomaly_df = pd.DataFrame()
                outbound_df = pd.DataFrame()
                anomaly_error_message = str(anomaly_error)
            comparison_df = build_period_model_comparison(
                model_df, outbound_df, production.data, today,
                days=DEFAULT_RECENT_DAYS,
                platform_days=production.effective_days,
            )
            forecast_model_df = build_prioritized_consumption_model(
                comparison_df, source_weights
            )
        else:
            outbound_df = pd.DataFrame()
            anomaly_df = pd.DataFrame()
            comparison_df = pd.DataFrame()
            forecast_model_df = production.data.rename(columns={
                "颜色": "color", "尺码": "size",
                "平台生产日均": "consumption_quantity",
            })
        if visible_sizes:
            forecast_model_df = forecast_model_df[
                forecast_model_df["size"].isin(visible_sizes)
            ]
        if forecast_model_df.empty:
            raise ValueError("最近30天暂无可用于点货预测的生产消耗数据")
        available_platforms = set(production.available_platforms)
        complete_platforms = set(production.included_platforms)
        missing_platforms = [
            platform for platform in DTF_PRODUCTION_PLATFORMS
            if platform not in available_platforms
        ]
        st.caption(
            "30天生产数据覆盖："
            f"完整 {len(complete_platforms)} 个平台｜"
            f"已有数据 {len(available_platforms)} 个平台"
            + (
                "｜尚无数据：" + "、".join(missing_platforms)
                if missing_platforms else ""
            )
        )
        forecast_model_df = render_forecast_usage_adjustment(
            forecast_model_df,
            production.total_quantity,
            DEFAULT_RECENT_DAYS,
            category,
            production.data,
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
            t("加权综合模型")
            if category == "黑白短袖" else "最近30天数据库生产消耗（可自定义）"
        )
    except Exception as e:
        st.info(t("暂无点货预测数据"))
        st.caption(str(e))
        return pd.DataFrame()

    st.subheader(t("点货预测表"))
    st.caption(t("库存按当前筛选材质合计，并合并同材质下的全部所选品牌。"))
    if category == "黑白短袖":
        st.caption(
            "本页只计算黑白短袖：使用订单、仓库每日出库和黑白短袖"
            "平台生产数据组成的可调权重模型。"
        )
    else:
        st.caption(
            "本页只计算彩色短袖：使用最近30天已保存的数据库生产消耗；"
            "平台日表缺失时自动使用已完成的系统扣减流水，"
            "不读取黑白短袖日耗或仓库每日出库。"
        )
    st.caption("当前品类的自定义日耗会同步更新其建议点货量和货柜联动。")
    render_reorder_forecast_table(forecast_df)
    if category == "黑白短袖":
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
    return forecast_model_df
