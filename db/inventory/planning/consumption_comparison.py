from datetime import timedelta

import pandas as pd

from db.inventory.core.constants import SIZE_COLUMNS


def build_period_model_comparison(model_df, outbound_df, current_date, days=14):
    if model_df.empty:
        return pd.DataFrame()

    model = (
        model_df.rename(columns={
            "color": "颜色",
            "size": "尺码",
            "consumption_quantity": "模型日耗",
        })
        .groupby(["颜色", "尺码"], as_index=False)["模型日耗"]
        .sum()
    )
    start_date = current_date - timedelta(days=int(days) - 1)
    recent = outbound_df[outbound_df["日期"] >= start_date].copy()
    recorded_days = int(recent["日期"].nunique()) if not recent.empty else 0

    if recent.empty:
        actual = pd.DataFrame(columns=["颜色", "尺码", "期间实际日均"])
    else:
        actual = (
            recent.groupby(["颜色", "尺码"], as_index=False)["实际出库"]
            .sum()
            .rename(columns={"实际出库": "期间实际日均"})
        )
        actual["期间实际日均"] = (
            actual["期间实际日均"] / recorded_days
        ).round().astype(int)

    result = model.merge(actual, on=["颜色", "尺码"], how="left")
    result["期间实际日均"] = pd.to_numeric(
        result["期间实际日均"], errors="coerce"
    ).fillna(0).astype(int)
    result["模型日耗"] = pd.to_numeric(
        result["模型日耗"], errors="coerce"
    ).fillna(0).astype(int)
    result["日均差额"] = result["期间实际日均"] - result["模型日耗"]
    result["差距%"] = result.apply(
        lambda row: round(row["日均差额"] / row["模型日耗"] * 100, 1)
        if row["模型日耗"] else None,
        axis=1,
    )
    result["有效出库天数"] = recorded_days
    result["_color"] = result["颜色"].map({"黑": 0, "白": 1}).fillna(99)
    result["_size"] = result["尺码"].map(
        {size: index for index, size in enumerate(SIZE_COLUMNS)}
    ).fillna(99)
    return (
        result.sort_values(["_color", "_size"])
        .drop(columns=["_color", "_size"])
        .reset_index(drop=True)
    )
