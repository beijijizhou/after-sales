from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


CACHE_VERSION = 2
CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "production_data"
NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class CachedProductionData:
    data: pd.DataFrame
    source: str
    saved_at: str


def load_production_cache(
    platform,
    start_date,
    end_date,
    start_hour=0,
    end_hour=23,
):
    key = _cache_key(platform, start_date, end_date, start_hour, end_hour)
    data_path = CACHE_DIR / f"{key}.parquet"
    metadata_path = CACHE_DIR / f"{key}.json"
    if not data_path.exists() or not metadata_path.exists():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        data = pd.read_parquet(data_path)
    except Exception:
        # A partial or incompatible local cache should behave like a cache miss.
        return None
    return CachedProductionData(
        data=data,
        source=str(metadata.get("source") or "本地生产数据"),
        saved_at=str(metadata.get("saved_at") or ""),
    )


def save_production_cache(
    platform,
    start_date,
    end_date,
    data,
    source,
    start_hour=0,
    end_hour=23,
):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _cache_key(platform, start_date, end_date, start_hour, end_hour)
    data_path = CACHE_DIR / f"{key}.parquet"
    metadata_path = CACHE_DIR / f"{key}.json"
    temporary_data = data_path.with_suffix(".parquet.tmp")
    temporary_metadata = metadata_path.with_suffix(".json.tmp")
    saved_at = datetime.now(NEW_YORK).strftime("%Y-%m-%d %H:%M:%S")
    data.to_parquet(temporary_data, index=False, compression="snappy")
    temporary_metadata.write_text(
        json.dumps(
            {
                "version": CACHE_VERSION,
                "platform": platform,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "start_hour": start_hour,
                "end_hour": end_hour,
                "rows": len(data),
                "source": source,
                "saved_at": saved_at,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary_data.replace(data_path)
    temporary_metadata.replace(metadata_path)
    return saved_at


def _cache_key(platform, start_date, end_date, start_hour, end_hour):
    query = "|".join([
        str(CACHE_VERSION),
        platform,
        start_date.isoformat(),
        end_date.isoformat(),
        str(start_hour),
        str(end_hour),
    ])
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:24]
