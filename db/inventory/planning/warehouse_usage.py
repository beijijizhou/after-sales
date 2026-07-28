from datetime import timedelta

import pandas as pd


INTERVAL_COLUMNS = [
    "颜色", "尺码", "上次出库日期", "本次出库日期",
    "出库间隔天数", "本次出库数量", "区间日均",
]


def build_warehouse_usage_intervals(outbound_df, current_date=None):
    if outbound_df.empty:
        return pd.DataFrame(columns=INTERVAL_COLUMNS)

    data = outbound_df.copy()
    if current_date:
        data = data[data["日期"] < current_date]
    data = (
        data.groupby(["日期", "颜色", "尺码"], as_index=False)["实际出库"]
        .sum()
        .sort_values(["颜色", "尺码", "日期"])
    )
    rows = []
    for (color, size), group in data.groupby(
        ["颜色", "尺码"], sort=False
    ):
        previous_date = None
        for row in group.to_dict("records"):
            current = row["日期"]
            if previous_date is not None:
                gap_days = (current - previous_date).days
                if gap_days > 0:
                    quantity = int(row["实际出库"])
                    rows.append({
                        "颜色": color,
                        "尺码": size,
                        "上次出库日期": previous_date,
                        "本次出库日期": current,
                        "出库间隔天数": gap_days,
                        "本次出库数量": quantity,
                        "区间日均": quantity / gap_days,
                    })
            previous_date = current
    return pd.DataFrame(rows, columns=INTERVAL_COLUMNS)


def build_warehouse_interval_average(
    outbound_df, current_date, days
):
    columns = ["颜色", "尺码", "仓库出库日均", "仓库区间数"]
    intervals = build_warehouse_usage_intervals(
        outbound_df, current_date
    )
    if intervals.empty:
        return pd.DataFrame(columns=columns), 0

    start_date = current_date - timedelta(days=int(days))
    recent = intervals[
        intervals["本次出库日期"] >= start_date
    ].copy()
    if recent.empty:
        return pd.DataFrame(columns=columns), 0

    result = (
        recent.groupby(["颜色", "尺码"], as_index=False)
        .agg(
            出库数量=("本次出库数量", "sum"),
            间隔天数=("出库间隔天数", "sum"),
            仓库区间数=("区间日均", "size"),
        )
    )
    result["仓库出库日均"] = (
        result["出库数量"] / result["间隔天数"]
    )
    return result[columns], int(len(recent))
