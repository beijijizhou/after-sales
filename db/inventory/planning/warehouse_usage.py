from datetime import timedelta

import pandas as pd
from db.inventory.core.constants import SIZE_COLUMNS


def build_stock_outbound_ratio_series(
    inventory_df, outbound_df, current_date, days=30, sizes=None,
):
    """Compare color/size shares of total stock and total 30-day manual issues."""
    sizes = [size for size in SIZE_COLUMNS if not sizes or size in sizes]
    stock = pd.DataFrame(inventory_df).copy()
    usage = pd.DataFrame(outbound_df).copy()
    stock_totals = {}
    for color in ("黑", "白"):
        selected = stock[stock["颜色"].eq(color)] if not stock.empty else stock
        for size in sizes:
            stock_totals[(color, size)] = pd.to_numeric(
                selected.get(size, pd.Series(dtype=float)), errors="coerce"
            ).fillna(0).clip(lower=0).sum()
    stock_total = sum(stock_totals.values())
    start = current_date - timedelta(days=days)
    if not usage.empty:
        usage["日期"] = pd.to_datetime(usage["日期"], errors="coerce").dt.date
        usage = usage[
            usage["日期"].ge(start) & usage["日期"].lt(current_date)
            & usage["颜色"].isin(("黑", "白")) & usage["尺码"].isin(sizes)
        ].copy()
        usage["实际出库"] = pd.to_numeric(usage["实际出库"], errors="coerce").fillna(0).clip(lower=0)
        usage_totals = usage.groupby(["颜色", "尺码"])["实际出库"].sum().to_dict()
        recorded_days = usage[usage["实际出库"].gt(0)]["日期"].nunique()
    else:
        usage_totals, recorded_days = {}, 0
    usage_total = sum(usage_totals.values())
    rows = []
    for (color, size), quantity in stock_totals.items():
        for series, value, denominator in (
            ("当前库存比例", quantity, stock_total),
            ("最近30天出库比例", usage_totals.get((color, size), 0), usage_total),
        ):
            rows.append({
                "颜色": color, "尺码": size, "颜色尺码": f"{color}{size}",
                "曲线": series, "占比": value / denominator if denominator > 0 else None,
                "数量": int(value), "总量": int(denominator),
                "开始日期": start, "结束日期": current_date - timedelta(days=1),
                "登记天数": int(recorded_days),
            })
    return pd.DataFrame(rows)


INTERVAL_COLUMNS = [
    "颜色", "尺码", "上次出库日期", "本次出库日期",
    "出库间隔天数", "本次出库数量", "区间日均",
]


def build_warehouse_daily_totals(outbound_df, current_date, days=30):
    """Summarize recorded warehouse outbound by complete business day."""
    columns = ["日期", "仓库出库量"]
    source = pd.DataFrame(outbound_df).copy()
    if source.empty or not {"日期", "实际出库"}.issubset(source.columns):
        return pd.DataFrame(columns=columns)
    source["日期"] = pd.to_datetime(source["日期"], errors="coerce").dt.date
    source["实际出库"] = pd.to_numeric(
        source["实际出库"], errors="coerce"
    ).fillna(0).clip(lower=0)
    start_date = current_date - timedelta(days=max(int(days), 1))
    source = source[
        source["日期"].ge(start_date) & source["日期"].lt(current_date)
    ]
    if source.empty:
        return pd.DataFrame(columns=columns)
    return (
        source.groupby("日期", as_index=False)["实际出库"]
        .sum()
        .rename(columns={"实际出库": "仓库出库量"})
        .sort_values("日期", ascending=False)
        .reset_index(drop=True)
    )


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
