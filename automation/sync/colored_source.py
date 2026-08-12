"""Read and audit cached colored-shirt production source data."""

import json

import pandas as pd

from automation.production import PLATFORMS_BY_DEPARTMENT
from automation.production_cache import CACHE_DIR
from utils.erp.catalog import normalize_color
from utils.erp.inventory_mapping import normalize_size


CATEGORY = "彩色短袖"
AGGREGATE_PLATFORM = "全部衣服平台"


def load_daily_colored_production_source(current_date, require_complete=False):
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


def list_colored_cached_dates(current_date, days=14):
    start_date = current_date.fromordinal(current_date.toordinal() - int(days) + 1)
    available = set()
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


def load_daily_colored_production(current_date, require_complete=False):
    detail, _ = load_daily_colored_production_source(current_date, require_complete)
    if detail.empty:
        return pd.DataFrame()
    return detail.groupby(["颜色", "尺码"], as_index=False)["生产数量"].sum()


def build_colored_platform_audit(current_date):
    detail, metadata = load_daily_colored_production_source(current_date)
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
