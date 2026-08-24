"""Pure summaries for database-backed Google manual registrations."""

import pandas as pd


MANUAL_NUMERIC_COLUMNS = (
    "registration_count", "film_quantity", "hoodie_registration_count",
    "hoodie_film_quantity", "multi_press_registration_count",
    "multi_press_quantity", "white_board_registration_count",
    "white_board_film_quantity",
)


def prepare_manual_analysis(rows):
    if rows.empty:
        return rows.copy()
    result = rows.copy()
    for column in MANUAL_NUMERIC_COLUMNS:
        if column not in result.columns:
            result[column] = 0
        result[column] = pd.to_numeric(
            result[column], errors="coerce"
        ).fillna(0).astype(int)
    result["business_date"] = pd.to_datetime(
        result["business_date"], errors="coerce"
    ).dt.date
    return result


def build_weekly_manual_summary(rows):
    if rows.empty:
        return pd.DataFrame()
    work = _with_week_start(rows)
    weekly = (
        work.groupby(["week_start", "platform"], as_index=False)
        .agg(**_manual_aggregations())
    )
    totals = weekly.groupby("week_start").agg(
        week_registrations=("registration_count", "sum"),
        week_film_quantity=("film_quantity", "sum"),
    )
    weekly = weekly.merge(totals, on="week_start", how="left")
    weekly["registration_share_percent"] = weekly.apply(
        lambda row: _share(
            row["registration_count"], row["week_registrations"]
        ), axis=1,
    )
    weekly["film_share_percent"] = weekly.apply(
        lambda row: _share(row["film_quantity"], row["week_film_quantity"]),
        axis=1,
    )
    _add_special_ratios(weekly)
    return weekly.sort_values(
        ["week_start", "registration_count"], ascending=[False, False]
    ).reset_index(drop=True)


def build_platform_person_summary(rows):
    if rows.empty:
        return pd.DataFrame()
    summary = (
        rows.groupby(["platform", "hotstamp_person"], as_index=False)
        .agg(**_manual_aggregations())
    )
    totals = summary.groupby("platform").agg(
        platform_registrations=("registration_count", "sum"),
        platform_film_quantity=("film_quantity", "sum"),
    )
    summary = summary.merge(totals, on="platform", how="left")
    summary["registration_share_percent"] = summary.apply(
        lambda row: _share(
            row["registration_count"], row["platform_registrations"]
        ), axis=1,
    )
    summary["film_share_percent"] = summary.apply(
        lambda row: _share(
            row["film_quantity"], row["platform_film_quantity"]
        ), axis=1,
    )
    return summary.sort_values(
        ["platform", "registration_count"], ascending=[True, False]
    ).reset_index(drop=True)


def build_person_manual_summary(rows):
    if rows.empty:
        return pd.DataFrame()
    work = rows.copy()
    work["hansen_registration_count"] = work["registration_count"].where(
        work["platform"] == "汉森", 0
    )
    summary = (
        work.groupby("hotstamp_person", as_index=False)
        .agg(
            **_manual_aggregations(),
            hansen_registration_count=("hansen_registration_count", "sum"),
        )
    )
    total_registrations = summary["registration_count"].sum()
    total_film = summary["film_quantity"].sum()
    summary["registration_share_percent"] = summary["registration_count"].apply(
        lambda value: _share(value, total_registrations)
    )
    summary["film_share_percent"] = summary["film_quantity"].apply(
        lambda value: _share(value, total_film)
    )
    _add_special_ratios(summary)
    summary["hansen_ratio_percent"] = summary.apply(
        lambda row: _share(
            row["hansen_registration_count"], row["registration_count"]
        ), axis=1,
    )
    return summary.sort_values(
        "registration_count", ascending=False
    ).reset_index(drop=True)


def build_daily_manual_summary(rows):
    if rows.empty:
        return pd.DataFrame()
    return (
        rows.groupby("business_date", as_index=False)
        .agg(**_manual_aggregations())
        .sort_values("business_date", ascending=False)
        .reset_index(drop=True)
    )


def _add_special_ratios(rows):
    rows["hoodie_ratio_percent"] = rows.apply(
        lambda row: _share(
            row["hoodie_registration_count"], row["registration_count"]
        ), axis=1,
    )
    rows["multi_press_ratio_percent"] = rows.apply(
        lambda row: _share(
            row["multi_press_registration_count"], row["registration_count"]
        ), axis=1,
    )


def _with_week_start(rows):
    work = rows.copy()
    dates = pd.to_datetime(work["business_date"], errors="coerce")
    work["week_start"] = (
        dates - pd.to_timedelta(dates.dt.weekday, unit="D")
    ).dt.date
    return work


def _manual_aggregations():
    return {
        column: (column, "sum") for column in MANUAL_NUMERIC_COLUMNS
    }


def _share(value, total):
    if total <= 0:
        return 0.0
    return round(value / total * 100, 1)
