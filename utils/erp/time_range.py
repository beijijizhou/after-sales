from datetime import datetime, time

import pandas as pd


TIME_COLUMNS = ("生产完成时间", "创建时间", "开始时间")


def build_hour_range(start_date, end_date, start_hour=0, end_hour=23):
    if not 0 <= start_hour <= 23 or not 0 <= end_hour <= 23:
        raise ValueError("查询小时必须在 0 至 23 之间")
    start_at = datetime.combine(start_date, time(start_hour))
    end_at = datetime.combine(end_date, time(end_hour, 59, 59, 999999))
    if start_at > end_at:
        raise ValueError("查询结束时间不能早于开始时间")
    return start_at, end_at


def filter_production_time(
    df,
    start_date,
    end_date,
    start_hour=0,
    end_hour=23,
):
    if df.empty:
        return df
    timestamps = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    for column in TIME_COLUMNS:
        if column in df.columns:
            values = pd.to_datetime(df[column], errors="coerce")
            timestamps = timestamps.fillna(values)
    if timestamps.notna().sum() == 0:
        return df
    start_at, end_at = build_hour_range(
        start_date, end_date, start_hour, end_hour
    )
    # Keep aggregate rows whose source does not expose individual timestamps.
    matches = timestamps.isna() | timestamps.between(start_at, end_at)
    return df.loc[matches].reset_index(drop=True)
