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
    included_platforms: tuple[str, ...] = ()
    coverage_ratio: float = 1.0
    estimate_method: str = "完整平台数据"

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
    platform_weights = _historical_complete_platform_weights(
        candidates, required,
        max(item["end_date"] for item in selected),
    )
    data, coverage_ratio, estimate_method = reweight_partial_production(
        data, included_platforms, required, platform_weights
    )
    return ProductionReference(
        data=data,
        start_date=min(item["start_date"] for item in selected),
        end_date=max(item["end_date"] for item in selected),
        saved_at=max(str(item.get("saved_at") or "") for item in selected),
        sources=len(selected),
        missing_platforms=tuple(sorted(missing)),
        included_platforms=tuple(sorted(included_platforms)),
        coverage_ratio=coverage_ratio,
        estimate_method=estimate_method,
    )


def reweight_partial_production(
    data, included_platforms, required_platforms, platform_weights=None,
):
    result = data.copy()
    required = set(required_platforms)
    included = set(included_platforms) & required
    if not required or required.issubset(included):
        return result, 1.0, "完整平台数据"
    weights = {
        str(platform): max(float(weight), 0)
        for platform, weight in (platform_weights or {}).items()
        if str(platform) in required
    }
    weight_total = sum(weights.values())
    if weight_total > 0:
        weights = {
            platform: weight / weight_total
            for platform, weight in weights.items()
        }
        coverage = sum(weights.get(platform, 0) for platform in included)
        method = "按最近完整生产数据的平台占比估算"
    else:
        coverage = len(included) / len(required) if required else 1.0
        method = "按可用平台数量等权估算"
    if coverage <= 0 or coverage >= 1 or result.empty:
        return result, max(min(coverage, 1.0), 0.0), method
    result["system_daily_usage"] = (
        pd.to_numeric(result["system_daily_usage"], errors="coerce")
        .fillna(0)
        / coverage
    )
    return result, coverage, method


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


def _historical_complete_platform_weights(items, required, cutoff_date):
    candidates = [
        item for item in items
        if item.get("platform") == AGGREGATE_PLATFORM
        and item.get("is_complete")
        and required.issubset(set(item.get("included_platforms") or []))
        and item["end_date"] <= cutoff_date
        and item["data_path"].exists()
    ]
    if not candidates:
        return {}
    selected = max(
        candidates,
        key=lambda item: (
            item["end_date"], _parse_saved_at(item.get("saved_at")),
            item["start_date"],
        ),
    )
    try:
        raw = pd.read_parquet(selected["data_path"])
    except Exception:
        return {}
    if not {"运营商", "数量"}.issubset(raw.columns):
        return {}
    quantities = pd.to_numeric(raw["数量"], errors="coerce").fillna(0)
    totals = (
        pd.DataFrame({"platform": raw["运营商"], "quantity": quantities})
        .groupby("platform", dropna=False)["quantity"].sum()
    )
    return {
        str(platform).strip(): float(quantity)
        for platform, quantity in totals.items()
        if str(platform).strip() in required and float(quantity) > 0
    }


def _required_platforms(department):
    return set(PLATFORMS_BY_DEPARTMENT.get(department, ()))
