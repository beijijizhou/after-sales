"""Pure comparison and balance models for the hotstamp-film audit."""

import pandas as pd


NUMERIC_COLUMNS = (
    "film_quantity", "system_scan_count", "system_piece_count",
    "source_entry_count", "hoodie_film_quantity", "hoodie_entry_count",
    "multi_press_quantity", "multi_press_entry_count",
)


def prepare_comparison(rows):
    if rows.empty:
        return rows.copy()
    result = rows.copy()
    for column in NUMERIC_COLUMNS:
        if column not in result.columns:
            result[column] = 0
        result[column] = pd.to_numeric(
            result[column], errors="coerce"
        ).fillna(0).astype(int)
    result["business_date"] = pd.to_datetime(
        result["business_date"], errors="coerce"
    ).dt.date
    result["scan_gap"] = result["film_quantity"] - result["system_scan_count"]
    result["piece_gap"] = result["film_quantity"] - result["system_piece_count"]
    result["match_status"] = result.apply(_match_status, axis=1)
    return result


def build_weekly_platform_allocation(comparison, tolerance_percent):
    """Summarize each worker's share inside one platform and week."""
    if comparison.empty:
        return pd.DataFrame()
    work = comparison.copy()
    dates = pd.to_datetime(work["business_date"], errors="coerce")
    work["week_start"] = (dates - pd.to_timedelta(dates.dt.weekday, unit="D")).dt.date
    grouped = (
        work.groupby(
            ["week_start", "platform", "hotstamp_person"], as_index=False
        )
        .agg(
            source_entry_count=("source_entry_count", "sum"),
            film_quantity=("film_quantity", "sum"),
            hoodie_film_quantity=("hoodie_film_quantity", "sum"),
            hoodie_entry_count=("hoodie_entry_count", "sum"),
            multi_press_quantity=("multi_press_quantity", "sum"),
            multi_press_entry_count=("multi_press_entry_count", "sum"),
            system_scan_count=("system_scan_count", "sum"),
            system_piece_count=("system_piece_count", "sum"),
        )
    )
    valid_people = grouped["hotstamp_person"] != "未填写烫印人员"
    active = valid_people & (
        (grouped["source_entry_count"] > 0) | (grouped["film_quantity"] > 0)
    )
    grouped["active_worker"] = active
    keys = ["week_start", "platform"]
    totals = (
        grouped.groupby(keys, as_index=False)
        .agg(
            platform_order_count=("source_entry_count", "sum"),
            platform_film_quantity=("film_quantity", "sum"),
            platform_hoodie_quantity=("hoodie_film_quantity", "sum"),
            platform_hoodie_entry_count=("hoodie_entry_count", "sum"),
            platform_multi_press_quantity=("multi_press_quantity", "sum"),
            platform_multi_press_entry_count=(
                "multi_press_entry_count", "sum"
            ),
        )
    )
    workers = (
        grouped[active].groupby(keys, as_index=False)["hotstamp_person"]
        .nunique().rename(columns={"hotstamp_person": "worker_count"})
    )
    grouped = grouped.merge(totals, on=keys, how="left").merge(
        workers, on=keys, how="left"
    )
    grouped["worker_count"] = grouped["worker_count"].fillna(0).astype(int)
    grouped["expected_share_percent"] = grouped["worker_count"].apply(
        lambda value: round(100 / value, 1) if value else 0.0
    )
    grouped["order_share_percent"] = grouped.apply(
        lambda row: _share(row["source_entry_count"], row["platform_order_count"]),
        axis=1,
    )
    grouped["order_deviation_percent"] = grouped.apply(
        lambda row: _relative_share_deviation(
            row["order_share_percent"], row["expected_share_percent"]
        ),
        axis=1,
    )
    grouped["allocation_status"] = grouped["order_deviation_percent"].apply(
        lambda value: _balance_status(value, tolerance_percent)
    )
    grouped.loc[~grouped["active_worker"], "allocation_status"] = "人员缺失"
    grouped["hoodie_allocation_share_percent"] = grouped.apply(
        lambda row: _share(
            row["hoodie_entry_count"], row["platform_hoodie_entry_count"]
        ), axis=1,
    )
    grouped["multi_press_allocation_share_percent"] = grouped.apply(
        lambda row: _share(
            row["multi_press_entry_count"],
            row["platform_multi_press_entry_count"],
        ), axis=1,
    )
    return grouped.sort_values(
        ["week_start", "platform", "source_entry_count"],
        ascending=[False, True, False],
    ).reset_index(drop=True)


def build_weekly_platform_summary(allocation, tolerance_percent):
    if allocation.empty:
        return pd.DataFrame()
    active = allocation[allocation["active_worker"]].copy()
    active["needs_attention"] = (
        active["order_deviation_percent"].abs() > tolerance_percent
    )
    summary = (
        active.groupby(["week_start", "platform"], as_index=False)
        .agg(
            order_count=("source_entry_count", "sum"),
            worker_count=("hotstamp_person", "nunique"),
            highest_order_share=("order_share_percent", "max"),
            lowest_order_share=("order_share_percent", "min"),
            attention_workers=("needs_attention", "sum"),
            film_quantity=("film_quantity", "sum"),
            hoodie_film_quantity=("hoodie_film_quantity", "sum"),
            hoodie_entry_count=("hoodie_entry_count", "sum"),
            multi_press_quantity=("multi_press_quantity", "sum"),
            multi_press_entry_count=("multi_press_entry_count", "sum"),
        )
    )
    summary["expected_share_percent"] = summary["worker_count"].apply(
        lambda value: round(100 / value, 1) if value else 0.0
    )
    summary["order_share_spread"] = (
        summary["highest_order_share"] - summary["lowest_order_share"]
    ).round(1)
    summary["hoodie_ratio_percent"] = summary.apply(
        lambda row: _share(row["hoodie_entry_count"], row["order_count"]),
        axis=1,
    )
    summary["multi_press_ratio_percent"] = summary.apply(
        lambda row: _share(row["multi_press_entry_count"], row["order_count"]),
        axis=1,
    )
    return summary.sort_values(
        ["attention_workers", "order_share_spread", "order_count"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def build_weekly_person_special_mix(comparison):
    """Show each worker's hoodie, multi-press and Hansen registration mix."""
    if comparison.empty:
        return pd.DataFrame()
    work = comparison.copy()
    dates = pd.to_datetime(work["business_date"], errors="coerce")
    work["week_start"] = (dates - pd.to_timedelta(dates.dt.weekday, unit="D")).dt.date
    work["hansen_order_count"] = work["source_entry_count"].where(
        work["platform"] == "汉森", 0
    )
    mix = (
        work.groupby(["week_start", "hotstamp_person"], as_index=False)
        .agg(
            order_count=("source_entry_count", "sum"),
            film_quantity=("film_quantity", "sum"),
            hoodie_film_quantity=("hoodie_film_quantity", "sum"),
            hoodie_entry_count=("hoodie_entry_count", "sum"),
            multi_press_quantity=("multi_press_quantity", "sum"),
            multi_press_entry_count=("multi_press_entry_count", "sum"),
            hansen_order_count=("hansen_order_count", "sum"),
        )
    )
    mix["hoodie_ratio_percent"] = mix.apply(
        lambda row: _share(row["hoodie_entry_count"], row["order_count"]),
        axis=1,
    )
    mix["multi_press_ratio_percent"] = mix.apply(
        lambda row: _share(row["multi_press_entry_count"], row["order_count"]),
        axis=1,
    )
    mix["hansen_ratio_percent"] = mix.apply(
        lambda row: _share(row["hansen_order_count"], row["order_count"]),
        axis=1,
    )
    return mix.sort_values("order_count", ascending=False).reset_index(drop=True)


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


def _share(value, total):
    if total <= 0:
        return 0.0
    return round(value / total * 100, 1)


def _relative_share_deviation(actual_share, expected_share):
    if expected_share <= 0:
        return 0.0
    return round((actual_share - expected_share) / expected_share * 100, 1)


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
