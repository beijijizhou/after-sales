from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.consumables.planning import (
    CONSUMABLE_LOOKBACK_DAYS,
    DEFAULT_COVERAGE_DAYS,
    build_consumable_consumption_model,
    build_consumable_reorder_forecast,
)
from ui.planning import render_planning_summary, render_target_days_input


NY_TIMEZONE = ZoneInfo("America/New_York")


def build_consumable_planning_frames(items_df, batches_df, movements_df):
    today = datetime.now(NY_TIMEZONE).date()
    return today, _build_frames(items_df, batches_df, movements_df, today)


def render_consumable_reorder_forecast(items_df, batches_df, movements_df):
    st.subheader("耗材点货预测")
    st.caption(
        "按最近领用记录生成耗材日均消耗，并给出当前库存可撑天数与建议点货量。"
    )
    _render_planning_controls()
    _today, frames = build_consumable_planning_frames(
        items_df, batches_df, movements_df
    )
    forecast_df = frames["forecast"]

    _render_summary_metrics(forecast_df)
    _render_forecast_table(forecast_df)


def render_consumable_consumption_model(
    items_df, batches_df, movements_df
):
    st.subheader("耗材消耗模型")
    st.caption("只统计有效领用批次；已撤销批次和撤销行不会进入模型。")
    st.caption(
        "本页复用“点货预测”的回看天数参数，不重复创建单独控件。"
    )
    _today, frames = build_consumable_planning_frames(
        items_df, batches_df, movements_df
    )
    _render_model_table(frames["model"])


def _render_planning_controls():
    col1, col2 = st.columns(2)
    lookback_days = col1.number_input(
        "消耗回看天数",
        min_value=7,
        max_value=60,
        value=CONSUMABLE_LOOKBACK_DAYS,
        step=1,
        key="consumable_planning_lookback_days",
    )
    coverage_days = render_target_days_input(
        col2,
        key="consumable_planning_coverage_days",
        default_days=DEFAULT_COVERAGE_DAYS,
        max_days=90,
    )
    return {
        "lookback_days": int(lookback_days),
        "coverage_days": int(coverage_days),
    }


def _build_frames(items_df, batches_df, movements_df, today):
    lookback_days = int(
        st.session_state.get(
            "consumable_planning_lookback_days",
            CONSUMABLE_LOOKBACK_DAYS,
        )
    )
    coverage_days = int(
        st.session_state.get(
            "consumable_planning_coverage_days",
            DEFAULT_COVERAGE_DAYS,
        )
    )
    model_df = build_consumable_consumption_model(
        items_df,
        batches_df,
        movements_df,
        lookback_days=lookback_days,
        current_date=today,
    )
    forecast_df = build_consumable_reorder_forecast(
        model_df,
        current_date=today,
        coverage_days=coverage_days,
    )
    return {"model": model_df, "forecast": forecast_df}


def _render_summary_metrics(forecast_df):
    if forecast_df.empty:
        st.info("暂无可用于预测的耗材 SKU。")
        return

    render_planning_summary(
        forecast_df,
        reorder_column="建议点货量",
        coverage_column="最低剩余天数",
        unit_column="基础单位",
    )


def _render_forecast_table(forecast_df):
    if forecast_df.empty:
        return
    display = forecast_df.copy()
    display = display.style.apply(_highlight_risk, axis=1)
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        column_config={
            "库存基准总数": st.column_config.NumberColumn(format="%.0f"),
            "预测日耗合计": st.column_config.NumberColumn(format="%.2f"),
            "最低剩余天数": st.column_config.NumberColumn(format="%d"),
            "最低库存": st.column_config.NumberColumn(format="%.0f"),
            "安全库存缺口": st.column_config.NumberColumn(format="%.0f"),
            "目标备货天数": st.column_config.NumberColumn(format="%d"),
            "建议点货量": st.column_config.NumberColumn(format="%.0f"),
            "建议点货量（箱）": st.column_config.NumberColumn(format="%.2f"),
            "有效数据天数": st.column_config.NumberColumn(format="%d"),
            "自然窗口日均": st.column_config.NumberColumn(format="%.2f"),
            "窗口天数": st.column_config.NumberColumn(format="%d"),
            "库存基准日期": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "当前日期": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "预计最早耗尽日期": st.column_config.DateColumn(format="YYYY-MM-DD"),
        },
    )


def _render_model_table(model_df):
    if model_df.empty:
        st.info("最近没有有效耗材领用记录，暂时无法形成消耗模型。")
        return
    st.dataframe(
        model_df,
        hide_index=True,
        width="stretch",
        column_config={
            "每箱数量": st.column_config.NumberColumn(format="%.2f"),
            "最近领用日均": st.column_config.NumberColumn(format="%.2f"),
            "有效数据天数": st.column_config.NumberColumn(format="%d"),
            "自然窗口日均": st.column_config.NumberColumn(format="%.2f"),
            "总领用量": st.column_config.NumberColumn(format="%.0f"),
            "窗口天数": st.column_config.NumberColumn(format="%d"),
            "当前库存": st.column_config.NumberColumn(format="%.0f"),
            "当前库存（箱）": st.column_config.NumberColumn(format="%.2f"),
            "最低库存": st.column_config.NumberColumn(format="%.0f"),
            "最低库存（箱）": st.column_config.NumberColumn(format="%.2f"),
        },
    )


def _highlight_risk(row):
    daily_usage = pd.to_numeric(row.get("预测日耗合计"), errors="coerce")
    coverage_days = pd.to_numeric(row.get("最低剩余天数"), errors="coerce")
    reorder_quantity = pd.to_numeric(row.get("建议点货量"), errors="coerce")
    styles = []
    for column in row.index:
        if pd.notna(reorder_quantity) and reorder_quantity > 0 and column in {
            "建议点货量", "建议点货量（箱）", "安全库存缺口",
        }:
            styles.append(
                "background-color: #fff1cc; color: #7a4a00; font-weight: 700;"
            )
        elif pd.notna(daily_usage) and daily_usage > 0 and pd.notna(coverage_days) and coverage_days < 14 and column in {
            "最低剩余天数", "预计最早耗尽日期",
        }:
            styles.append(
                "background-color: #ffe0e0; color: #8a0000; font-weight: 700;"
            )
        else:
            styles.append("")
    return styles
