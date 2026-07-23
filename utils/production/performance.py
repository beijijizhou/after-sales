from datetime import datetime

import pandas as pd

from utils.production.constants import NY_TIMEZONE


def build_daily_performance_index(
    rows, minimum_output=500, minimum_baseline_days=3
):
    if rows.empty:
        return pd.DataFrame()
    people = rows.groupby(["日期", "人员"], as_index=False).agg(
        产量=("产量", "sum"),
        first_scan_at=("first_scan_at", "min"),
        last_scan_at=("last_scan_at", "max"),
    )
    people["工作小时"] = (
        people["last_scan_at"] - people["first_scan_at"]
    ).dt.total_seconds().div(3600).clip(lower=0)
    people = people[
        (people["产量"] >= minimum_output)
        & (people["工作小时"] > 0)
    ].copy()
    if people.empty:
        return pd.DataFrame()

    people["个人时产"] = people["产量"] / people["工作小时"]
    today = datetime.now(NY_TIMEZONE).date()
    baseline_source = people[
        pd.to_datetime(people["日期"]).dt.date != today
    ]
    baselines = baseline_source.groupby("人员", as_index=False).agg(
        基准天数=("日期", "nunique"),
        个人基准时产=("个人时产", "median"),
    )
    baselines = baselines[
        (baselines["基准天数"] >= minimum_baseline_days)
        & (baselines["个人基准时产"] > 0)
    ]
    people = people.merge(baselines, on="人员", how="inner")
    if people.empty:
        return pd.DataFrame()

    people["个人表现指数"] = (
        people["个人时产"] / people["个人基准时产"] * 100
    )
    daily = people.groupby("日期", as_index=False).agg(
        团队表现指数=("个人表现指数", "median"),
        有效人数=("人员", "nunique"),
    )
    daily["团队表现指数"] = daily["团队表现指数"].round(1)
    return classify_daily_performance(daily)


def classify_daily_performance(daily):
    result = daily.copy()
    result["时产状态"] = "正常"
    result.loc[result["团队表现指数"] >= 110, "时产状态"] = "高产"
    result.loc[result["团队表现指数"] <= 90, "时产状态"] = "偏低"
    today = datetime.now(NY_TIMEZONE).date()
    result.loc[
        pd.to_datetime(result["日期"]).dt.date == today,
        "时产状态",
    ] = "进行中"
    return result
