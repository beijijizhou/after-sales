from dataclasses import dataclass
from datetime import date, timedelta
import json

import pandas as pd

from automation.production import DTF_PRODUCTION_PLATFORMS
from automation.production_batch import ALL_CLOTHING_PLATFORMS
from automation.production_cache import CACHE_DIR
from automation.production_cache import load_production_cache
from db.production_consumption import (
    load_daily_platform_consumption,
    load_platform_sync_coverage,
)
from utils.erp.catalog import normalize_color
from utils.erp.inventory_mapping import normalize_size


DEFAULT_RECENT_DAYS = 30


@dataclass(frozen=True)
class PeriodProductionModel:
    data: pd.DataFrame
    effective_days: int
    start_date: date | None
    end_date: date | None
    total_quantity: float = 0
    requested_days: int = 0
    included_platforms: tuple = ()
    available_platforms: tuple = ()


def load_recent_production_model(
    current_date, days, category, supabase=None,
):
    """Load one recent complete-day window from the unified production fact."""
    requested_days = max(int(days), 1)
    end_date = current_date - timedelta(days=1)
    start_date = end_date - timedelta(days=requested_days - 1)
    if supabase is not None:
        try:
            persisted = load_daily_platform_consumption(
                supabase, "DTF", category, start_date, end_date
            )
            coverage = load_platform_sync_coverage(
                supabase, "DTF", category, start_date, end_date
            )
            if not persisted.empty:
                rows = persisted.rename(columns={
                    "color": "颜色", "size": "尺码",
                })
                included = tuple(sorted(
                    platform for platform, dates in coverage.items()
                    if len(dates) >= requested_days
                ))
                available = tuple(sorted(
                    persisted["platform"].dropna().astype(str).unique()
                ))
                return _build_recent_model(
                    rows, "quantity", requested_days, start_date, end_date,
                    included, available,
                )
        except Exception:
            # Deployment may not have the unified fact tables yet. The exact
            # aggregate cache remains a valid, reviewable fallback.
            pass
    cached = load_production_cache(
        ALL_CLOTHING_PLATFORMS, start_date, end_date
    )
    if cached is None:
        return PeriodProductionModel(
            pd.DataFrame(), 0, None, None,
            requested_days=requested_days,
        )
    raw = cached.data.copy()
    required = {"部门", "品类", "颜色", "尺码", "数量"}
    if not required.issubset(raw.columns):
        return PeriodProductionModel(
            pd.DataFrame(), 0, None, None,
            requested_days=requested_days,
        )
    if "生产项状态" in raw:
        raw = raw[
            ~raw["生产项状态"].astype(str).str.contains("取消", na=False)
        ]
    rows = raw[(raw["部门"] == "DTF") & (raw["品类"] == category)]
    metadata = cached.metadata or {}
    available = set(metadata.get("available_platforms") or ())
    if "运营商" in rows:
        available.update(rows["运营商"].dropna().astype(str).unique())
    return _build_recent_model(
        rows, "数量", requested_days, start_date, end_date,
        tuple(metadata.get("included_platforms") or ()),
        tuple(sorted(available)),
    )


def load_period_production_model(current_date, days, category):
    start_date = current_date - timedelta(days=int(days) - 1)
    candidates = _complete_aggregate_caches(start_date, current_date)
    selected, covered = _select_non_overlapping(candidates)
    frames = []
    for item in selected:
        try:
            raw = pd.read_parquet(item["data_path"])
        except Exception:
            continue
        if "生产项状态" in raw:
            raw = raw[
                ~raw["生产项状态"].astype(str).str.contains(
                    "取消", na=False
                )
            ]
        normalized = raw[
            (raw["部门"] == "DTF")
            & (raw["品类"] == category)
        ]
        frame = pd.DataFrame({
            "color": normalized["颜色"].map(normalize_color),
            "size": normalized["尺码"].map(normalize_size),
            "quantity": normalized["数量"],
        })
        frames.append(frame)

    effective_days = len(covered)
    if not frames or effective_days == 0:
        return PeriodProductionModel(pd.DataFrame(), 0, None, None)
    data = pd.concat(frames, ignore_index=True)
    data["quantity"] = pd.to_numeric(
        data["quantity"], errors="coerce"
    ).fillna(0)
    data = (
        data.groupby(["color", "size"], as_index=False)["quantity"]
        .sum()
        .rename(columns={"color": "颜色", "size": "尺码"})
    )
    data["平台生产日均"] = data["quantity"] / effective_days
    return PeriodProductionModel(
        data[["颜色", "尺码", "平台生产日均"]],
        effective_days,
        min(covered),
        max(covered),
    )


def _complete_aggregate_caches(start_date, end_date):
    candidates = []
    required = set(DTF_PRODUCTION_PLATFORMS)
    for path in CACHE_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            if item.get("platform") != ALL_CLOTHING_PLATFORMS:
                continue
            item["start_date"] = date.fromisoformat(item["start_date"])
            item["end_date"] = date.fromisoformat(item["end_date"])
            item["data_path"] = path.with_suffix(".parquet")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if (
            item["start_date"] < start_date
            or item["end_date"] > end_date
            or not item["data_path"].exists()
        ):
            continue
        included = set(item.get("included_platforms") or [])
        if not item.get("is_complete") or not required.issubset(included):
            continue
        item["period_start"] = item["start_date"]
        item["period_end"] = item["end_date"]
        candidates.append(item)
    return candidates


def _select_non_overlapping(candidates):
    selected, covered = [], set()
    ranked = sorted(
        candidates,
        key=lambda item: (
            (item["period_end"] - item["period_start"]).days,
            str(item.get("saved_at") or ""),
        ),
        reverse=True,
    )
    for item in ranked:
        dates = {
            item["period_start"] + timedelta(days=offset)
            for offset in range(
                (item["period_end"] - item["period_start"]).days + 1
            )
        }
        if dates & covered:
            continue
        selected.append(item)
        covered.update(dates)
    return selected, covered


def _build_recent_model(
    rows, quantity_field, days, start_date, end_date,
    included_platforms=(), available_platforms=(),
):
    source = pd.DataFrame(rows).copy()
    if source.empty:
        return PeriodProductionModel(
            pd.DataFrame(), days, start_date, end_date, 0, days,
            tuple(included_platforms), tuple(available_platforms),
        )
    source["颜色"] = source["颜色"].map(normalize_color)
    source["尺码"] = source["尺码"].map(normalize_size)
    source[quantity_field] = pd.to_numeric(
        source[quantity_field], errors="coerce"
    ).fillna(0).clip(lower=0)
    total_quantity = float(source[quantity_field].sum())
    data = source.groupby(
        ["颜色", "尺码"], as_index=False
    )[quantity_field].sum()
    data["平台生产日均"] = data[quantity_field] / int(days)
    return PeriodProductionModel(
        data[["颜色", "尺码", "平台生产日均"]],
        int(days), start_date, end_date, total_quantity, int(days),
        tuple(included_platforms), tuple(available_platforms),
    )
