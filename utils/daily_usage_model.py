from datetime import timedelta

import pandas as pd


EFFECTIVE_DAYS_PER_KEY_ACTIVITY = "per_key_activity"
EFFECTIVE_DAYS_GLOBAL_WINDOW = "global_window"
EFFECTIVE_DAYS_GLOBAL_SINCE_FIRST = "global_since_first"


def build_daily_usage_summary(
    daily_rows,
    keys,
    quantity_column,
    current_date,
    window_days,
    *,
    date_column="日期",
    effective_day_mode=EFFECTIVE_DAYS_PER_KEY_ACTIVITY,
    observation_dates=None,
    usage_column="每日消耗",
    effective_days_column="有效数据天数",
    natural_usage_column="自然日均消耗",
    total_usage_column="窗口总消耗",
    window_days_column="窗口天数",
    round_digits=1,
):
    columns = [
        *keys,
        usage_column,
        effective_days_column,
        natural_usage_column,
        total_usage_column,
        window_days_column,
    ]
    frame = pd.DataFrame(daily_rows).copy()
    if frame.empty or current_date is None:
        return pd.DataFrame(columns=columns)

    end_date = pd.Timestamp(current_date).date()
    lookback = max(int(window_days), 1)
    start_date = end_date - timedelta(days=lookback - 1)
    frame[date_column] = pd.to_datetime(
        frame[date_column], errors="coerce"
    ).dt.date
    frame = frame[frame[date_column].between(start_date, end_date)].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)

    frame[quantity_column] = pd.to_numeric(
        frame[quantity_column], errors="coerce"
    ).fillna(0)
    grouped = frame.groupby(
        [*keys, date_column], as_index=False
    )[quantity_column].sum()
    grouped = grouped[grouped[quantity_column] > 0].copy()
    if grouped.empty:
        return pd.DataFrame(columns=columns)

    normalized_observation_dates = _normalize_observation_dates(
        observation_dates, grouped[date_column].tolist(), start_date, end_date
    )
    summary = grouped.groupby(keys, as_index=False).agg(
        **{
            total_usage_column: (quantity_column, "sum"),
            "_first_usage_date": (date_column, "min"),
            "_active_days": (date_column, "nunique"),
        }
    )
    summary[effective_days_column] = summary.apply(
        lambda row: _effective_days(
            row["_first_usage_date"],
            int(row["_active_days"]),
            normalized_observation_dates,
            effective_day_mode,
        ),
        axis=1,
    )
    summary[window_days_column] = lookback
    summary[natural_usage_column] = (
        summary[total_usage_column] / lookback
    ).round(round_digits)
    summary[usage_column] = summary.apply(
        lambda row: round(
            float(row[total_usage_column]) / int(row[effective_days_column]),
            round_digits,
        ) if int(row[effective_days_column]) > 0 else 0,
        axis=1,
    )
    return summary[columns].reset_index(drop=True)


def _normalize_observation_dates(
    observation_dates, fallback_dates, start_date, end_date
):
    source = observation_dates if observation_dates is not None else fallback_dates
    normalized = []
    for value in source:
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            continue
        normalized.append(parsed.date())
    normalized = sorted(set(normalized))
    return [
        value for value in normalized
        if start_date <= value <= end_date
    ]


def _effective_days(
    first_usage_date,
    active_days,
    observation_dates,
    effective_day_mode,
):
    if effective_day_mode == EFFECTIVE_DAYS_PER_KEY_ACTIVITY:
        return int(active_days)
    if effective_day_mode == EFFECTIVE_DAYS_GLOBAL_WINDOW:
        return len(observation_dates)
    if effective_day_mode == EFFECTIVE_DAYS_GLOBAL_SINCE_FIRST:
        return sum(value >= first_usage_date for value in observation_dates)
    raise ValueError(f"Unsupported effective_day_mode: {effective_day_mode}")
