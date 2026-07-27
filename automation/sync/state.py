from contextlib import contextmanager
from datetime import datetime, timedelta
import fcntl
from zoneinfo import ZoneInfo

from automation.production import DTF_PRODUCTION_PLATFORMS
from automation.production_batch import ALL_CLOTHING_PLATFORMS
from automation.production_cache import CACHE_DIR, load_production_cache
from automation.sync.cache_seed import find_covering_cache


NEW_YORK = ZoneInfo("America/New_York")
LOCK_PATH = CACHE_DIR / "daily-sync.lock"


def lookback_dates(days):
    yesterday = datetime.now(NEW_YORK).date() - timedelta(days=1)
    start = yesterday - timedelta(days=max(int(days), 1) - 1)
    return [
        start + timedelta(days=offset)
        for offset in range((yesterday - start).days + 1)
    ]


def is_complete(cached):
    return bool(cached and cached.metadata.get("is_complete"))


def list_sync_status(lookback_days=7):
    rows = []
    for day in lookback_dates(lookback_days):
        cached = load_production_cache(
            ALL_CLOTHING_PLATFORMS, day, day
        )
        covering = None if cached else find_covering_cache(day)
        state = (
            "完整" if is_complete(cached)
            else "可从区间缓存拆分" if covering
            else "缺失"
        )
        rows.append({
            "date": day,
            "state": state,
            "saved_at": (
                cached.saved_at if cached
                else str(covering[0].get("saved_at") or "")
                if covering else ""
            ),
            "missing": (
                cached.metadata.get("missing_platforms", [])
                if cached else []
                if covering else list(DTF_PRODUCTION_PLATFORMS)
            ),
        })
    return rows


@contextmanager
def single_instance():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("生产数据同步已经在运行") from error
        yield
