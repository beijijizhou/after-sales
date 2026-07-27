from datetime import date
import json

import pandas as pd

from automation.production import DTF_PRODUCTION_PLATFORMS
from automation.production_batch import ALL_CLOTHING_PLATFORMS
from automation.production_cache import CACHE_DIR, save_production_cache
from utils.erp.time_range import filter_production_time


def seed_daily_cache_from_period(target_date):
    source = find_covering_cache(target_date)
    if source is None:
        return None
    metadata, data_path = source
    try:
        period_data = pd.read_parquet(data_path)
    except Exception:
        return None

    daily = filter_production_time(
        period_data, target_date, target_date, 0, 23
    )
    saved_at = str(metadata.get("saved_at") or "")
    source_label = (
        f"完整区间缓存 {metadata['start_date']} 至 "
        f"{metadata['end_date']} 的单日拆分"
    )
    for platform in DTF_PRODUCTION_PLATFORMS:
        platform_data = daily[
            daily["运营商"].astype(str) == platform
        ].copy()
        save_production_cache(
            platform,
            target_date,
            target_date,
            platform_data,
            source_label,
            saved_at=saved_at,
        )
    save_production_cache(
        ALL_CLOTHING_PLATFORMS,
        target_date,
        target_date,
        daily,
        source_label,
        extra_metadata={
            "included_platforms": list(DTF_PRODUCTION_PLATFORMS),
            "missing_platforms": [],
            "is_complete": True,
            "derived_from": data_path.name,
        },
        saved_at=saved_at,
    )
    return len(daily)


def find_covering_cache(target_date):
    candidates = []
    required = set(DTF_PRODUCTION_PLATFORMS)
    for path in CACHE_DIR.glob("*.json"):
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
            start = date.fromisoformat(metadata["start_date"])
            end = date.fromisoformat(metadata["end_date"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if (
            metadata.get("platform") != ALL_CLOTHING_PLATFORMS
            or not metadata.get("is_complete")
            or not required.issubset(
                set(metadata.get("included_platforms") or [])
            )
            or not (start <= target_date <= end)
            or start == end
        ):
            continue
        data_path = path.with_suffix(".parquet")
        if data_path.exists():
            candidates.append((
                (end - start).days,
                str(metadata.get("saved_at") or ""),
                metadata,
                data_path,
            ))
    if not candidates:
        return None
    shortest_period = min(item[0] for item in candidates)
    _, _, metadata, data_path = max(
        (
            item for item in candidates
            if item[0] == shortest_period
        ),
        key=lambda item: item[1],
    )
    return metadata, data_path
