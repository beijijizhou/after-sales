"""Canonical daily-usage contract for every inventory planning source."""

import pandas as pd


USAGE_VALUE_COLUMNS = [
    "daily_usage",
    "effective_days",
    "window_days",
    "total_usage",
    "usage_source_type",
    "usage_source_label",
]


def empty_daily_usage_contract(key_columns):
    return pd.DataFrame(columns=[*key_columns, *USAGE_VALUE_COLUMNS])


def build_daily_usage_contract(
    source_df,
    *,
    key_columns,
    daily_usage_column,
    source_type,
    source_label,
    effective_days_column=None,
    window_days_column=None,
    total_usage_column=None,
):
    """Normalize one source model before it enters inventory planning.

    Source adapters retain their own extraction and business-day policy. This
    boundary standardizes the resulting daily rate, evidence window, and source
    attribution so downstream planning does not depend on source column names.
    """

    columns = [*key_columns, *USAGE_VALUE_COLUMNS]
    result = pd.DataFrame(source_df).copy()
    if result.empty:
        return empty_daily_usage_contract(key_columns)
    missing = [column for column in key_columns if column not in result]
    if missing or daily_usage_column not in result:
        raise ValueError(
            "日耗模型缺少标准字段："
            + "、".join([*missing, *(
                [daily_usage_column]
                if daily_usage_column not in result else []
            )])
        )

    for column in key_columns:
        result[column] = result[column].fillna("").astype(str).str.strip()
    result["daily_usage"] = pd.to_numeric(
        result[daily_usage_column], errors="coerce"
    ).fillna(0).clip(lower=0)
    result["effective_days"] = _numeric_column(
        result, effective_days_column
    )
    result["window_days"] = _numeric_column(result, window_days_column)
    result["total_usage"] = _numeric_column(result, total_usage_column)
    result["usage_source_type"] = str(source_type or "").strip()
    result["usage_source_label"] = str(source_label or "").strip()

    aggregations = {
        "daily_usage": "sum",
        "effective_days": "max",
        "window_days": "max",
        "total_usage": "sum",
        "usage_source_type": "first",
        "usage_source_label": "first",
    }
    return result.groupby(
        list(key_columns), dropna=False, as_index=False
    ).agg(aggregations)[columns]


def _numeric_column(frame, column):
    if not column or column not in frame:
        return pd.Series(0.0, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0).clip(lower=0)
