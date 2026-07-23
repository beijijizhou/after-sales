from datetime import timedelta

import pandas as pd

from db.inventory.core.constants import SIZE_COLUMNS


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
    result["15,000模型日耗"] = pd.to_numeric(
        result["15,000模型日耗"], errors="coerce"
    ).fillna(0)
    result["仓库/模型"] = _percentage(
        result["仓库出库日均"], result["15,000模型日耗"]
    )
    result["平台/模型"] = _percentage(
        result["平台生产日均"], result["15,000模型日耗"]
    )
    result["仓库有效天数"] = warehouse_days
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
    start_date = current_date - timedelta(days=int(days) - 1)
    recent = outbound_df[outbound_df["日期"] >= start_date].copy()
    recorded_days = int(recent["日期"].nunique()) if not recent.empty else 0
    if not recorded_days:
        return pd.DataFrame(columns=columns), 0
    average = (
        recent.groupby(["颜色", "尺码"], as_index=False)["实际出库"]
        .sum()
        .rename(columns={"实际出库": "仓库出库日均"})
    )
    average["仓库出库日均"] = (
        average["仓库出库日均"] / recorded_days
    )
    return average, recorded_days


def _percentage(values, baseline):
    denominator = baseline.where(baseline > 0)
    return values / denominator * 100
