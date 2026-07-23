from datetime import timedelta

import pandas as pd

from utils.production.constants import HALOO_PLATFORM, NY_TIMEZONE
from utils.production.normalization import normalize_platform
from utils.production.platform_summary import (
    finalize_person_platform_summary,
)


def get_period_dates(selected_date, days=14):
    return selected_date - timedelta(days=days - 1), selected_date


def filter_period_rows(
    rows, start_date, end_date, people=None, client_type="全部",
    platforms=None,
):
    if rows.empty:
        return rows
    start_at = pd.Timestamp(start_date)
    end_at = pd.Timestamp(end_date)
    result = rows[
        rows["日期"].between(start_at, end_at, inclusive="both")
    ]
    if people:
        result = result[result["人员"].isin(people)]
    if client_type == HALOO_PLATFORM:
        result = result[result["平台"] == HALOO_PLATFORM]
    elif client_type == "小平台":
        result = result[result["平台"] != HALOO_PLATFORM]
    if platforms:
        result = result[result["平台"].isin(platforms)]
    return result.reset_index(drop=True)


def prepare_period_rows(rows):
    required = {
        "work_date", "person", "platform", "scan_count",
        "multiple_order_count", "first_scan_at", "last_scan_at",
    }
    if rows.empty or not required.issubset(rows.columns):
        return pd.DataFrame()

    result = rows.copy()
    result["日期"] = pd.to_datetime(result["work_date"], errors="coerce")
    result["人员"] = result["person"].astype(str).str.strip()
    result["平台"] = result["platform"].apply(normalize_platform)
    result["产量"] = pd.to_numeric(
        result["scan_count"], errors="coerce"
    ).fillna(0).astype(int)
    result["多件数量"] = pd.to_numeric(
        result["multiple_order_count"], errors="coerce"
    ).fillna(0).astype(int)
    result["first_scan_at"] = pd.to_datetime(
        result["first_scan_at"], errors="coerce", utc=True
    ).dt.tz_convert(NY_TIMEZONE)
    result["last_scan_at"] = pd.to_datetime(
        result["last_scan_at"], errors="coerce", utc=True
    ).dt.tz_convert(NY_TIMEZONE)
    return result.dropna(subset=["日期"])[[
        "日期", "人员", "平台", "产量", "多件数量",
        "first_scan_at", "last_scan_at",
    ]]


def build_daily_summary(rows, start_date, end_date):
    dates = pd.DataFrame({
        "日期": pd.date_range(start_date, end_date, freq="D")
    })
    if rows.empty:
        return dates.assign(
            总产量=0, 多件数量=0, Haloo=0, 小平台=0,
            多件占比=0.0, 人均小时产量=0.0, 参与人数=0,
        )

    daily_source = rows.assign(
        Haloo产量=rows["产量"].where(
            rows["平台"] == HALOO_PLATFORM, 0
        )
    )
    daily = daily_source.groupby("日期", as_index=False).agg(
        总产量=("产量", "sum"),
        多件数量=("多件数量", "sum"),
        Haloo=("Haloo产量", "sum"),
    )
    daily["小平台"] = daily["总产量"] - daily["Haloo"]
    daily["多件占比"] = (
        daily["多件数量"] / daily["总产量"] * 100
    ).fillna(0).round(1)
    productivity = build_daily_productivity(rows)
    daily = daily.merge(productivity, on="日期", how="left")
    result = dates.merge(daily, on="日期", how="left").fillna({
        "总产量": 0, "多件数量": 0, "Haloo": 0, "小平台": 0,
        "多件占比": 0, "人均小时产量": 0, "参与人数": 0,
    })
    for column in [
        "总产量", "多件数量", "Haloo", "小平台", "参与人数",
    ]:
        result[column] = result[column].astype(int)
    return result


def build_daily_productivity(rows):
    people = rows.groupby(["日期", "人员"], as_index=False).agg(
        产量=("产量", "sum"),
        first_scan_at=("first_scan_at", "min"),
        last_scan_at=("last_scan_at", "max"),
    )
    people["工作小时"] = (
        people["last_scan_at"] - people["first_scan_at"]
    ).dt.total_seconds().div(3600).clip(lower=0)

    results = []
    for work_date, day in people.groupby("日期"):
        eligible = day[day["产量"] >= 500]
        working_hours = float(day["工作小时"].max()) if not day.empty else 0
        rate = (
            eligible["产量"].sum() / len(eligible) / working_hours
            if len(eligible) and working_hours > 0 else 0
        )
        results.append({
            "日期": work_date,
            "人均小时产量": round(rate, 1),
            "参与人数": len(eligible),
        })
    return pd.DataFrame(results)


def build_platform_summary(rows):
    if rows.empty:
        return pd.DataFrame(columns=["平台", "产量", "占比"])
    summary = rows.groupby("平台", as_index=False)["产量"].sum()
    total = summary["产量"].sum()
    summary["占比"] = (
        summary["产量"] / total * 100 if total else 0
    ).round(1)
    return summary.sort_values("产量", ascending=False).reset_index(drop=True)


def build_period_person_platform_summary(rows):
    if rows.empty:
        return pd.DataFrame()
    pivot = rows.pivot_table(
        index="人员", columns="平台", values="产量",
        fill_value=0, aggfunc="sum",
    ).reset_index()
    platform_columns = [
        column for column in pivot.columns if column != "人员"
    ]
    pivot["总生产数量"] = pivot[platform_columns].sum(axis=1)
    multiple = (
        rows.groupby("人员", as_index=False)["多件数量"].sum()
        .rename(columns={"多件数量": "多件订单数量"})
    )
    person_days = rows.groupby(["日期", "人员"], as_index=False).agg(
        first_scan_at=("first_scan_at", "min"),
        last_scan_at=("last_scan_at", "max"),
    )
    person_days["working_hours"] = (
        person_days["last_scan_at"] - person_days["first_scan_at"]
    ).dt.total_seconds().div(3600).clip(lower=0)
    working_hours = (
        person_days.groupby("人员", as_index=False)["working_hours"].sum()
    )
    pivot = pivot.merge(multiple, on="人员", how="left")
    pivot = pivot.merge(working_hours, on="人员", how="left")
    return finalize_person_platform_summary(pivot, platform_columns)
