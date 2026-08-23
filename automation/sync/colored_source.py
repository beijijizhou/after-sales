"""Read and audit cached colored-shirt production source data."""

import json

import pandas as pd

from automation.production import PLATFORMS_BY_DEPARTMENT
from automation.production_cache import CACHE_DIR
from automation.sync.daily import COLORED_PRIMARY_PLATFORMS
from db.production_consumption import (
    load_daily_platform_consumption,
    load_platform_sync_coverage,
)
from utils.erp.catalog import normalize_color
from utils.erp.inventory_mapping import normalize_size


CATEGORY = "彩色短袖"
AGGREGATE_PLATFORM = "全部衣服平台"


def load_daily_colored_production_source(
    current_date, require_complete=False, supabase=None,
):
    if supabase is not None:
        persisted = _load_persisted_daily_source(supabase, current_date)
        if persisted is not None:
            detail, metadata = persisted
            if require_complete and not metadata.get("is_complete"):
                return pd.DataFrame(), metadata
            return detail, metadata
    candidates = []
    for path in CACHE_DIR.glob("*.json"):
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            metadata.get("platform") == AGGREGATE_PLATFORM
            and metadata.get("start_date") == current_date.isoformat()
            and metadata.get("end_date") == current_date.isoformat()
            and path.with_suffix(".parquet").exists()
        ):
            candidates.append((str(metadata.get("saved_at") or ""), path))
    if not candidates:
        return pd.DataFrame(), {}
    metadata_path = max(candidates)[1]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if require_complete and not metadata.get("is_complete"):
        return pd.DataFrame(), metadata
    raw = pd.read_parquet(metadata_path.with_suffix(".parquet"))
    if "生产项状态" in raw:
        raw = raw[~raw["生产项状态"].astype(str).str.contains("取消", na=False)]
    daily = raw[(raw["部门"] == "DTF") & (raw["品类"] == CATEGORY)].copy()
    if daily.empty:
        return pd.DataFrame(), metadata
    daily["数量"] = pd.to_numeric(daily["数量"], errors="coerce").fillna(0)
    daily["原始颜色"] = daily["颜色"].fillna("").astype(str).str.strip()
    daily["原始尺码"] = daily["尺码"].fillna("").astype(str).str.strip()
    daily["颜色"] = daily["颜色"].map(normalize_color)
    daily["尺码"] = daily["尺码"].map(normalize_size)
    if "运营商" not in daily:
        daily["运营商"] = "未标记平台"
    daily["运营商"] = daily["运营商"].fillna("").astype(str).str.strip().replace(
        "", "未标记平台"
    )
    detail = daily.groupby(
        ["运营商", "原始颜色", "原始尺码", "颜色", "尺码"], as_index=False,
    ).agg(生产数量=("数量", "sum"), 生产记录数=("数量", "size"))
    return detail, metadata


def list_colored_cached_dates(current_date, days=14, supabase=None):
    start_date = current_date.fromordinal(current_date.toordinal() - int(days) + 1)
    available = set()
    if supabase is not None:
        persisted = load_daily_platform_consumption(
            supabase, "DTF", CATEGORY, start_date, current_date
        )
        if not persisted.empty:
            available.update(
                pd.to_datetime(
                    persisted["business_date"], errors="coerce"
                ).dropna().dt.date
            )
    for path in CACHE_DIR.glob("*.json"):
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
            target = current_date.fromisoformat(metadata["start_date"])
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if (
            metadata.get("platform") == AGGREGATE_PLATFORM
            and metadata.get("start_date") == metadata.get("end_date")
            and start_date <= target <= current_date
            and path.with_suffix(".parquet").exists()
        ):
            available.add(target)
    return sorted(available, reverse=True)


def load_daily_colored_production(
    current_date, require_complete=False, supabase=None,
):
    detail, _ = load_daily_colored_production_source(
        current_date, require_complete, supabase=supabase
    )
    if detail.empty:
        return pd.DataFrame()
    return detail.groupby(["颜色", "尺码"], as_index=False)["生产数量"].sum()


def build_colored_platform_audit(current_date, supabase=None):
    detail, metadata = load_daily_colored_production_source(
        current_date, supabase=supabase
    )
    quantities = detail.groupby("运营商")["生产数量"].sum().to_dict() if not detail.empty else {}
    counts = detail.groupby("运营商")["生产记录数"].sum().to_dict() if not detail.empty else {}
    included = {str(value).strip() for value in metadata.get("included_platforms") or []}
    missing = {str(value).strip() for value in metadata.get("missing_platforms") or []}
    configured = list(PLATFORMS_BY_DEPARTMENT.get("DTF", ()))
    extras = sorted((set(quantities) | included | missing) - set(configured))
    rows = []
    for platform in [*configured, *extras]:
        status = (
            "读取失败/缺失" if platform in missing
            else "已读取" if platform in included or platform in quantities
            else "未确认"
        )
        rows.append({
            "平台": platform, "读取状态": status,
            "原始生产件数": int(quantities.get(platform, 0)),
            "生产记录数": int(counts.get(platform, 0)),
        })
    return pd.DataFrame(rows), metadata


def _load_persisted_daily_source(supabase, current_date):
    rows = load_daily_platform_consumption(
        supabase, "DTF", CATEGORY, current_date, current_date
    )
    coverage = load_platform_sync_coverage(
        supabase, "DTF", CATEGORY, current_date, current_date
    )
    included = {
        platform for platform, dates in coverage.items()
        if current_date in dates
    }
    if rows.empty and not included:
        return None
    configured = set(PLATFORMS_BY_DEPARTMENT.get("DTF", ()))
    missing = configured - included
    metadata = {
        "source": "数据库生产日表",
        "included_platforms": sorted(included),
        "missing_platforms": sorted(missing),
        "is_complete": configured.issubset(included),
        "colored_primary_complete": set(
            COLORED_PRIMARY_PLATFORMS
        ).issubset(included),
    }
    if rows.empty:
        return pd.DataFrame(), metadata
    detail = rows.rename(columns={
        "platform": "运营商",
        "color": "原始颜色",
        "size": "原始尺码",
        "quantity": "生产数量",
        "record_count": "生产记录数",
    }).copy()
    detail["颜色"] = detail["原始颜色"].map(normalize_color)
    detail["尺码"] = detail["原始尺码"].map(normalize_size)
    detail["生产数量"] = pd.to_numeric(
        detail["生产数量"], errors="coerce"
    ).fillna(0)
    detail["生产记录数"] = pd.to_numeric(
        detail["生产记录数"], errors="coerce"
    ).fillna(0).astype(int)
    return detail[[
        "运营商", "原始颜色", "原始尺码", "颜色", "尺码",
        "生产数量", "生产记录数",
    ]], metadata
