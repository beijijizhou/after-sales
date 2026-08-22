"""Pure comparison and balance models for the hotstamp-film audit."""

import pandas as pd


NUMERIC_COLUMNS = (
    "film_quantity", "system_scan_count", "system_piece_count",
)


def prepare_comparison(rows):
    if rows.empty:
        return rows.copy()
    result = rows.copy()
    for column in NUMERIC_COLUMNS:
        result[column] = pd.to_numeric(
            result.get(column, 0), errors="coerce"
        ).fillna(0).astype(int)
    result["business_date"] = pd.to_datetime(
        result["business_date"], errors="coerce"
    ).dt.date
    result["scan_gap"] = result["film_quantity"] - result["system_scan_count"]
    result["piece_gap"] = result["film_quantity"] - result["system_piece_count"]
    result["match_status"] = result.apply(_match_status, axis=1)
    return result


def build_daily_person_balance(comparison, tolerance_percent):
    if comparison.empty:
        return pd.DataFrame()
    daily = (
        comparison.groupby(["business_date", "hotstamp_person"], as_index=False)
        .agg(
            film_quantity=("film_quantity", "sum"),
            system_scan_count=("system_scan_count", "sum"),
            system_piece_count=("system_piece_count", "sum"),
        )
    )
    film_people = daily[
        (daily["film_quantity"] > 0)
        & (daily["hotstamp_person"] != "未填写烫印人员")
    ]
    averages = (
        film_people.groupby("business_date", as_index=False)["film_quantity"]
        .mean().rename(columns={"film_quantity": "team_average"})
    )
    daily = daily.merge(averages, on="business_date", how="left")
    daily["team_average"] = daily["team_average"].fillna(0)
    daily["balance_deviation_percent"] = daily.apply(
        lambda row: _deviation(row["film_quantity"], row["team_average"]),
        axis=1,
    )
    daily["balance_status"] = daily["balance_deviation_percent"].apply(
        lambda value: _balance_status(value, tolerance_percent)
    )
    daily.loc[
        daily["hotstamp_person"] == "未填写烫印人员", "balance_status"
    ] = "人员缺失"
    daily.loc[
        (daily["film_quantity"] <= 0)
        & (daily["system_scan_count"] > 0),
        "balance_status",
    ] = "表格无登记"
    daily["scan_gap"] = daily["film_quantity"] - daily["system_scan_count"]
    daily["piece_gap"] = daily["film_quantity"] - daily["system_piece_count"]
    return daily.sort_values(
        ["business_date", "film_quantity"], ascending=[False, False]
    ).reset_index(drop=True)


def build_person_summary(daily_balance, tolerance_percent):
    if daily_balance.empty:
        return pd.DataFrame()
    work = daily_balance.copy()
    work["is_unbalanced"] = (
        work["balance_deviation_percent"].abs() > tolerance_percent
    )
    summary = (
        work.groupby("hotstamp_person", as_index=False)
        .agg(
            active_days=("business_date", "nunique"),
            film_quantity=("film_quantity", "sum"),
            system_scan_count=("system_scan_count", "sum"),
            system_piece_count=("system_piece_count", "sum"),
            unbalanced_days=("is_unbalanced", "sum"),
            max_deviation_percent=("balance_deviation_percent", lambda v: v.abs().max()),
        )
    )
    summary["scan_gap"] = summary["film_quantity"] - summary["system_scan_count"]
    summary["piece_gap"] = summary["film_quantity"] - summary["system_piece_count"]
    summary["balance_status"] = summary.apply(
        lambda row: _person_status(row, tolerance_percent), axis=1
    )
    return summary.sort_values(
        ["unbalanced_days", "max_deviation_percent", "film_quantity"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def _match_status(row):
    if row["film_quantity"] <= 0 and row["system_scan_count"] > 0:
        return "表格无登记"
    if row["film_quantity"] > 0 and row["system_scan_count"] <= 0:
        return "系统无记录"
    if row["film_quantity"] == row["system_scan_count"]:
        return "一致"
    return "有差异"


def _deviation(value, average):
    if average <= 0:
        return 0.0
    return round((value - average) / average * 100, 1)


def _balance_status(deviation, tolerance):
    absolute = abs(float(deviation))
    if absolute <= tolerance:
        return "均匀"
    if absolute <= tolerance * 2:
        return "需关注"
    return "偏差明显"


def _person_status(row, tolerance):
    if row["hotstamp_person"] == "未填写烫印人员":
        return "人员缺失"
    if row["unbalanced_days"] == 0:
        return "均匀"
    if row["max_deviation_percent"] <= tolerance * 2:
        return "需关注"
    return "偏差明显"
