from dataclasses import dataclass
from datetime import date, datetime
import json

import pandas as pd

from automation.production_cache import CACHE_DIR
from automation.production import (
    PLATFORMS_BY_DEPARTMENT,
)
from utils.erp.inventory_mapping import (
    KEY_COLUMNS,
    normalize_production_for_inventory,
)


AGGREGATE_PLATFORM = "全部衣服平台"


@dataclass(frozen=True)
class ProductionReference:
    data: pd.DataFrame
    start_date: date | None
    end_date: date | None
    saved_at: str
    sources: int
    missing_platforms: tuple[str, ...]

    @property
    def is_complete(self):
        return not self.missing_platforms


def load_production_reference(department, category=None):
    candidates = _load_metadata()
    if department == "DTF":
        candidates = [
            item for item in candidates
            if item["platform"] == AGGREGATE_PLATFORM
        ]
    else:
        candidates = [
            item for item in candidates
            if item["platform"] != AGGREGATE_PLATFORM
        ]
    selected = _latest_cache_per_platform(candidates)
    frames = []
    included_platforms = set()
    for item in selected:
        try:
            raw = pd.read_parquet(item["data_path"])
        except Exception:
            continue
        normalized = normalize_production_for_inventory(raw)
        included_platforms.update(
            raw.get("运营商", pd.Series(dtype="object"))
            .dropna().astype(str).str.strip()
        )
        included_platforms.update(item.get("included_platforms") or [])
        normalized = normalized[normalized["department"] == department]
        if category:
            normalized = normalized[normalized["category"] == category]
        if "生产项状态" in normalized.columns:
            normalized = normalized[
                ~normalized["生产项状态"].astype(str).str.contains(
                    "取消", na=False
                )
            ]
        days = max((item["end_date"] - item["start_date"]).days + 1, 1)
        normalized["system_daily_usage"] = normalized["quantity"] / days
        frames.append(normalized[[*KEY_COLUMNS, "system_daily_usage"]])

    if not frames:
        required = _required_platforms(department)
        return ProductionReference(
            pd.DataFrame(), None, None, "", 0, tuple(sorted(required))
        )
    data = (
        pd.concat(frames, ignore_index=True)
        .groupby(KEY_COLUMNS, dropna=False, as_index=False)
        .agg(system_daily_usage=("system_daily_usage", "sum"))
    )
    required = _required_platforms(department)
    declared_missing = {
        str(value) for item in selected
        for value in item.get("missing_platforms") or []
    }
    missing = (required - included_platforms) | declared_missing
    return ProductionReference(
        data=data,
        start_date=min(item["start_date"] for item in selected),
        end_date=max(item["end_date"] for item in selected),
        saved_at=max(str(item.get("saved_at") or "") for item in selected),
        sources=len(selected),
        missing_platforms=tuple(sorted(missing)),
    )


def _load_metadata():
    result = []
    if not CACHE_DIR.exists():
        return result
    for path in CACHE_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            item["start_date"] = date.fromisoformat(item["start_date"])
            item["end_date"] = date.fromisoformat(item["end_date"])
            item["data_path"] = path.with_suffix(".parquet")
            if item["data_path"].exists():
                result.append(item)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return result


def _latest_cache_per_platform(items):
    selected = {}
    for item in items:
        platform = str(item.get("platform") or "")
        saved_at = _parse_saved_at(item.get("saved_at"))
        rank = (item["end_date"], saved_at, item["start_date"])
        if platform not in selected or rank > selected[platform][0]:
            selected[platform] = (rank, item)
    return [value[1] for value in selected.values()]


def _parse_saved_at(value):
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return datetime.min


def _required_platforms(department):
    return set(PLATFORMS_BY_DEPARTMENT.get(department, ()))
