from dataclasses import dataclass
from datetime import date, timedelta
import json

import pandas as pd

from automation.production import DTF_PRODUCTION_PLATFORMS
from automation.production_batch import ALL_CLOTHING_PLATFORMS
from automation.production_cache import CACHE_DIR
from utils.erp.catalog import normalize_color
from utils.erp.inventory_mapping import normalize_size


@dataclass(frozen=True)
class PeriodProductionModel:
    data: pd.DataFrame
    effective_days: int
    start_date: date | None
    end_date: date | None


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
