from datetime import timedelta

import pandas as pd

from db.inventory.core.constants import SIZE_COLUMNS


FORECAST_SOURCE_WEIGHTS = {
    "15,000模型日耗": 0.60,
    "平台生产日均": 0.30,
    "仓库出库日均": 0.10,
}


def normalize_forecast_weights(source_weights=None):
    weights = {
        field: max(float(value), 0)
        for field, value in (
            source_weights or FORECAST_SOURCE_WEIGHTS
        ).items()
    }
    total = sum(weights.values())
    if total <= 0:
        return FORECAST_SOURCE_WEIGHTS.copy()
    return {
        field: value / total
        for field, value in weights.items()
    }


def build_prioritized_consumption_model(
    comparison_df, source_weights=None
):
    columns = ["color", "size", "consumption_quantity"]
    if comparison_df.empty:
        return pd.DataFrame(columns=columns)

    source_weights = normalize_forecast_weights(source_weights)
    rows = []
    for row in comparison_df.to_dict("records"):
        weighted_total = 0.0
        available_weight = 0.0
        for field, weight in source_weights.items():
            value = pd.to_numeric(row.get(field), errors="coerce")
            if pd.isna(value):
                continue
            weighted_total += max(float(value), 0) * weight
            available_weight += weight
        rows.append({
            "color": row.get("颜色"),
            "size": row.get("尺码"),
            "consumption_quantity": (
                round(weighted_total / available_weight)
                if available_weight else 0
            ),
        })
    return pd.DataFrame(rows, columns=columns)


def build_period_model_comparison(
    model_df, outbound_df, platform_df, current_date, days=14,
    platform_days=0,
):
    if model_df.empty:
        return pd.DataFrame()
    model = (
        model_df.rename(columns={
            "color": "颜色", "size": "尺码",
            "consumption_quantity": "15,000模型日耗",
        })
        .groupby(["颜色", "尺码"], as_index=False)["15,000模型日耗"]
        .sum()
    )
    warehouse, warehouse_days = _warehouse_average(
        outbound_df, current_date, days
    )
    result = model.merge(warehouse, on=["颜色", "尺码"], how="left")
    if not platform_df.empty:
        result = result.merge(
            platform_df, on=["颜色", "尺码"], how="left"
        )
    if "平台生产日均" not in result:
        result["平台生产日均"] = pd.NA
    for column in ["仓库出库日均", "平台生产日均"]:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    if warehouse_days:
        result["仓库出库日均"] = result["仓库出库日均"].fillna(0)
    if platform_days:
        result["平台生产日均"] = result["平台生产日均"].fillna(0)
    result["15,000模型日耗"] = pd.to_numeric(
        result["15,000模型日耗"], errors="coerce"
    ).fillna(0)
    result["三模型平均日耗"] = result[
        ["15,000模型日耗", "仓库出库日均", "平台生产日均"]
    ].mean(axis=1, skipna=True)
    result["仓库/模型"] = _percentage(
        result["仓库出库日均"], result["15,000模型日耗"]
    )
    result["平台/模型"] = _percentage(
        result["平台生产日均"], result["15,000模型日耗"]
    )
    result["仓库有效天数"] = warehouse_days
    result["仓库统计天数"] = int(days)
    result["平台有效天数"] = int(platform_days)
    result["_color"] = result["颜色"].map({"黑": 0, "白": 1}).fillna(99)
    result["_size"] = result["尺码"].map(
        {size: index for index, size in enumerate(SIZE_COLUMNS)}
    ).fillna(99)
    return (
        result.sort_values(["_color", "_size"])
        .drop(columns=["_color", "_size"])
        .reset_index(drop=True)
    )


def _warehouse_average(outbound_df, current_date, days):
    columns = ["颜色", "尺码", "仓库出库日均"]
    if outbound_df.empty:
        return pd.DataFrame(columns=columns), 0
    end_date = current_date - timedelta(days=1)
    start_date = end_date - timedelta(days=int(days) - 1)
    recent = outbound_df[
        (outbound_df["日期"] >= start_date)
        & (outbound_df["日期"] <= end_date)
    ].copy()
    recorded_days = int(recent["日期"].nunique()) if not recent.empty else 0
    if not recorded_days:
        return pd.DataFrame(columns=columns), 0
    average = (
        recent.groupby(["颜色", "尺码"], as_index=False)["实际出库"]
        .sum()
        .rename(columns={"实际出库": "仓库出库日均"})
    )
    average["仓库出库日均"] = (
        average["仓库出库日均"] / int(days)
    )
    return average, recorded_days


def _percentage(values, baseline):
    denominator = baseline.where(baseline > 0)
    return values / denominator * 100


def build_model_accuracy_summary(comparison_df):
    if comparison_df.empty:
        return pd.DataFrame()
    actual = pd.to_numeric(
        comparison_df["平台生产日均"], errors="coerce"
    )
    valid = actual.notna()
    if not valid.any():
        return pd.DataFrame()

    rows = []
    for field, label in [
        ("15,000模型日耗", "15,000模型"),
        ("仓库出库日均", "仓库出库模型"),
    ]:
        predicted = pd.to_numeric(
            comparison_df[field], errors="coerce"
        )
        comparable = valid & predicted.notna()
        if not comparable.any():
            continue
        absolute_error = (
            predicted[comparable] - actual[comparable]
        ).abs().sum()
        actual_total = actual[comparable].sum()
        error_rate = (
            float(absolute_error / actual_total * 100)
            if actual_total > 0 else None
        )
        rows.append({
            "模型": label,
            "与平台数据偏差": error_rate,
            "匹配度": max(0.0, 100.0 - error_rate)
            if error_rate is not None else None,
        })
    return pd.DataFrame(rows).sort_values(
        "与平台数据偏差", na_position="last"
    ).reset_index(drop=True)
