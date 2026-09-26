"""Shared consumption model built from audited manual inventory outbound."""

from dataclasses import dataclass

import pandas as pd

from db.inventory.planning.demand_anomaly import load_daily_outbound_history
from db.planning import build_daily_usage_contract
from utils.daily_usage_model import (
    EFFECTIVE_DAYS_GLOBAL_WINDOW,
    build_daily_usage_summary,
)
from utils.erp.inventory_mapping import KEY_COLUMNS


SKU_DIMENSIONS = ["品牌", "材质", "颜色", "尺码"]


@dataclass(frozen=True)
class OutboundConsumption:
    history: pd.DataFrame
    model: pd.DataFrame
    usage: pd.DataFrame
    recorded_days: int
    window_days: int


def load_outbound_consumption(
    supabase, department, category, current_date, window_days=30, **filters,
):
    """Load one category's outbound evidence and produce shared planning data."""
    history = load_daily_outbound_history(
        supabase, department, category, current_date,
        lookback_days=max(int(window_days), 1), **filters,
    )
    model = build_outbound_consumption_model(
        history, current_date, window_days
    )
    usage = build_outbound_forecast_usage(model, department, category)
    return OutboundConsumption(
        history=history,
        model=model,
        usage=usage,
        recorded_days=(
            int(history["日期"].nunique()) if not history.empty else 0
        ),
        window_days=max(int(window_days), 1),
    )


def build_outbound_consumption_model(history, current_date, window_days=30):
    """Calculate SKU usage against the category's recorded outbound dates.

    Every detailed SKU row uses the same denominator.  This keeps the
    row-level evidence reviewable without turning a brand/material that first
    appears on a later date into a new daily demand stream when the rows are
    combined for planning.
    """
    columns = [
        *SKU_DIMENSIONS, "每日消耗", "有效数据天数", "自然日均消耗",
        "窗口总消耗", "窗口天数",
    ]
    source = pd.DataFrame(history).copy()
    if source.empty:
        return pd.DataFrame(columns=columns)
    for column in SKU_DIMENSIONS:
        if column not in source:
            source[column] = ""
        source[column] = source[column].fillna("").astype(str).str.strip()
    source["尺码"] = source["尺码"].str.upper()
    observation_dates = sorted(pd.to_datetime(
        source["日期"], errors="coerce"
    ).dropna().dt.date.unique())
    return build_daily_usage_summary(
        source, SKU_DIMENSIONS, "实际出库", current_date, window_days,
        date_column="日期",
        effective_day_mode=EFFECTIVE_DAYS_GLOBAL_WINDOW,
        observation_dates=observation_dates,
        usage_column="每日消耗",
        effective_days_column="有效数据天数",
        natural_usage_column="自然日均消耗",
        total_usage_column="窗口总消耗",
        window_days_column="窗口天数",
        round_digits=1,
    )[columns]


def build_outbound_forecast_usage(model, department, category):
    """Adapt the shared outbound model to the canonical planning contract."""
    source = pd.DataFrame(model).copy()
    if source.empty:
        return build_daily_usage_contract(
            pd.DataFrame(columns=[*KEY_COLUMNS, "daily_usage"]),
            key_columns=KEY_COLUMNS, daily_usage_column="daily_usage",
            source_type="warehouse_outbound", source_label="仓库每日出库",
        )
    source = source.rename(columns={
        "材质": "planning_material", "颜色": "color", "尺码": "size",
        "每日消耗": "daily_usage", "有效数据天数": "effective_days",
        "窗口总消耗": "total_usage", "窗口天数": "window_days",
    })
    source["department"] = str(department or "").strip()
    source["category"] = str(category or "").strip()
    if source["department"].eq("DTF").all():
        source["planning_material"] = "全部品牌/材质"
    return build_daily_usage_contract(
        source,
        key_columns=KEY_COLUMNS,
        daily_usage_column="daily_usage",
        effective_days_column="effective_days",
        window_days_column="window_days",
        total_usage_column="total_usage",
        source_type="warehouse_outbound",
        source_label="仓库每日出库",
    )


def apparel_forecast_model(usage):
    """Return the color/size contract used by apparel reorder calculations."""
    source = pd.DataFrame(usage).copy()
    columns = ["color", "size", "consumption_quantity"]
    if source.empty:
        return pd.DataFrame(columns=columns)
    return (
        source.groupby(["color", "size"], as_index=False)["daily_usage"]
        .sum().rename(columns={"daily_usage": "consumption_quantity"})
    )[columns]
