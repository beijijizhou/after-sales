"""Bounded Humbird production reads for unusually busy business days."""

import pandas as pd


SUBDAY_WINDOWS = ((0, 5), (6, 11), (12, 17), (18, 23))


def is_result_limit_error(error):
    message = str(error).lower()
    return any(marker in message for marker in (
        "超过1w", "超过 1w", "超过10000", "exceeds 10000",
    ))


def load_busy_day_chunks(loader, platform, target_date, credentials):
    frames = []
    for start_hour, end_hour in SUBDAY_WINDOWS:
        result = loader(
            platform, target_date, target_date,
            credentials=credentials,
            start_hour=start_hour,
            end_hour=end_hour,
        )
        frames.append(result.data)
    data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return data, f"{platform} 单日高峰分时 API / {len(data):,} 条"
