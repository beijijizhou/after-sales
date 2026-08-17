"""Parallel multi-platform API refresh for colored-shirt history."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import timedelta

import pandas as pd

from automation.production import DTF_PRODUCTION_PLATFORMS, load_production_data
from automation.production_batch import ALL_CLOTHING_PLATFORMS
from automation.production_cache import load_production_cache, save_production_cache
from automation.sync.credentials import load_platform_credentials
from db.production_consumption import (
    load_daily_platform_consumption,
    load_platform_sync_coverage,
    replace_daily_platform_consumption,
)
from utils.erp.catalog import normalize_color
from utils.erp.inventory_mapping import normalize_size


CATEGORY = "彩色短袖"
LOOKBACK_DAYS = 30


@dataclass(frozen=True)
class ColoredApiPeriodModel:
    data: pd.DataFrame
    start_date: object
    end_date: object
    covered_days: int
    included_platforms: tuple
    missing_platforms: tuple
    available_platforms: tuple = ()
    coverage_days: dict = field(default_factory=dict)
    platform_errors: dict = field(default_factory=dict)
    persistence_errors: dict = field(default_factory=dict)
    storage_error: str | None = None
    source: str = "empty"


def load_colored_api_period_model(
    current_date, days=LOOKBACK_DAYS, supabase=None,
):
    end_date = current_date - timedelta(days=1)
    start_date = end_date - timedelta(days=int(days) - 1)
    storage_error = None
    if supabase is not None:
        try:
            persisted = load_daily_platform_consumption(
                supabase, "DTF", CATEGORY, start_date, end_date
            )
        except Exception as error:
            storage_error = str(error)
        else:
            coverage = {}
            try:
                coverage = load_platform_sync_coverage(
                    supabase, "DTF", CATEGORY, start_date, end_date
                )
            except Exception as error:
                storage_error = str(error)
            included = tuple(sorted(
                platform for platform, dates in coverage.items()
                if len(dates) >= int(days)
            ))
            if not persisted.empty or included:
                model = _model_from_persisted(persisted, days)
                available = tuple(sorted(
                    set(persisted.get("platform", pd.Series(dtype=str))
                        .dropna().astype(str))
                ))
                coverage_days = {
                    platform: len(dates) for platform, dates in coverage.items()
                }
                missing = tuple(
                    platform for platform in DTF_PRODUCTION_PLATFORMS
                    if platform not in included
                )
                return ColoredApiPeriodModel(
                    model, start_date, end_date, int(days), included, missing,
                    available, coverage_days,
                    storage_error=storage_error,
                    source="database",
                )
    cached = load_production_cache(
        ALL_CLOTHING_PLATFORMS, start_date, end_date
    )
    if cached is None:
        return ColoredApiPeriodModel(
            pd.DataFrame(), start_date, end_date, 0, (),
            tuple(DTF_PRODUCTION_PLATFORMS),
            storage_error=storage_error,
            source="empty",
        )
    rows = cached.data.copy()
    required = {"部门", "品类", "颜色", "尺码", "数量"}
    if not required.issubset(rows.columns):
        rows = pd.DataFrame(columns=sorted(required))
    if "生产项状态" in rows:
        rows = rows[
            ~rows["生产项状态"].astype(str).str.contains("取消", na=False)
        ]
    rows = rows[(rows["部门"] == "DTF") & (rows["品类"] == CATEGORY)]
    if rows.empty:
        model = pd.DataFrame(columns=["颜色", "尺码", "平台生产日均"])
    else:
        rows = rows.copy()
        rows["颜色"] = rows["颜色"].map(normalize_color)
        rows["尺码"] = rows["尺码"].map(normalize_size)
        rows["数量"] = pd.to_numeric(rows["数量"], errors="coerce").fillna(0)
        model = rows.groupby(["颜色", "尺码"], as_index=False)["数量"].sum()
        model["平台生产日均"] = model["数量"] / int(days)
        model = model[["颜色", "尺码", "平台生产日均"]]
    metadata = cached.metadata or {}
    available = set(metadata.get("available_platforms") or ())
    if "运营商" in rows:
        available.update(
            rows["运营商"].dropna().astype(str).loc[lambda value: value.ne("")]
        )
    return ColoredApiPeriodModel(
        model, start_date, end_date, int(days),
        tuple(metadata.get("included_platforms") or ()),
        tuple(metadata.get("missing_platforms") or ()),
        tuple(sorted(available)),
        dict(metadata.get("platform_coverage_days") or {}),
        dict(metadata.get("platform_errors") or {}),
        dict(metadata.get("persistence_errors") or {}),
        storage_error,
        "local_cache",
    )


def build_colored_platform_status(model, platforms=None):
    configured = tuple(platforms or DTF_PRODUCTION_PLATFORMS)
    included = set(model.included_platforms)
    missing = set(model.missing_platforms)
    available = set(getattr(model, "available_platforms", ()) or ())
    coverage = getattr(model, "coverage_days", {}) or {}
    api_errors = _errors_by_platform(
        getattr(model, "platform_errors", {}) or {}
    )
    persistence_errors = _errors_by_platform(
        getattr(model, "persistence_errors", {}) or {}
    )
    extras = sorted(
        (included | missing | available | set(coverage)) - set(configured)
    )
    return pd.DataFrame([
        {
            "平台": platform,
            "读取状态": _platform_state(
                platform, included, available, coverage,
                api_errors, persistence_errors,
            ),
            "数据期间": _platform_period(
                platform, model, included, available, coverage
            ),
            "下一步": _platform_next_step(
                platform, included, available, coverage,
                api_errors, persistence_errors,
            ),
        }
        for platform in (*configured, *extras)
    ])


def refresh_colored_api_period(
    current_date, secrets, days=LOOKBACK_DAYS, chunk_days=7,
    max_workers=8, report_progress=None, supabase=None, operator="system",
):
    end_date = current_date - timedelta(days=1)
    start_date = end_date - timedelta(days=int(days) - 1)
    chunks = _date_chunks(start_date, end_date, chunk_days)
    report = report_progress or (lambda _done, _total, _message: None)
    credentials, credential_errors = {}, {}
    for platform in DTF_PRODUCTION_PLATFORMS:
        try:
            credentials[platform] = load_platform_credentials(platform, secrets)
        except Exception as error:
            credential_errors[platform] = str(error)

    tasks = [
        (platform, chunk_start, chunk_end)
        for platform in DTF_PRODUCTION_PLATFORMS
        if platform not in credential_errors
        for chunk_start, chunk_end in chunks
    ]
    frames, errors = [], dict(credential_errors)
    persistence_errors = {}
    coverage_days = {platform: 0 for platform in DTF_PRODUCTION_PLATFORMS}
    completed = 0
    with ThreadPoolExecutor(
        max_workers=max(1, min(int(max_workers), len(tasks) or 1))
    ) as executor:
        futures = {
            executor.submit(
                _load_chunk, platform, chunk_start, chunk_end,
                credentials.get(platform),
            ): (platform, chunk_start, chunk_end)
            for platform, chunk_start, chunk_end in tasks
        }
        for future in as_completed(futures):
            platform, chunk_start, chunk_end = futures[future]
            completed += 1
            try:
                frame, source = future.result()
                frames.append(frame)
                coverage_days[platform] += (chunk_end - chunk_start).days + 1
                if supabase is not None:
                    for category in ("黑白短袖", "彩色短袖"):
                        try:
                            replace_daily_platform_consumption(
                                supabase, "DTF", category, platform,
                                chunk_start, chunk_end, frame, source, operator,
                            )
                        except Exception as error:
                            persistence_errors[
                                f"{platform}:{category}:{chunk_start}:{chunk_end}"
                            ] = str(error)
                message = f"{platform} {chunk_start:%m/%d}-{chunk_end:%m/%d}"
            except Exception as error:
                errors[f"{platform}:{chunk_start}:{chunk_end}"] = str(error)
                message = f"{platform} 分片读取失败"
            report(completed, len(tasks), message)

    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    failed_platforms = {
        key.split(":", 1)[0] for key in errors
    }
    included = sorted(set(DTF_PRODUCTION_PLATFORMS) - failed_platforms)
    available = sorted({
        str(value) for value in combined.get(
            "运营商", pd.Series(dtype=str)
        ).dropna().astype(str) if str(value)
    })
    save_production_cache(
        ALL_CLOTHING_PLATFORMS, start_date, end_date, combined,
        f"最近 {days} 天彩色短袖平台 API 并发读取",
        extra_metadata={
            "included_platforms": included,
            "missing_platforms": sorted(failed_platforms),
            "available_platforms": available,
            "platform_coverage_days": coverage_days,
            "platform_errors": errors,
            "persistence_errors": persistence_errors,
            "is_complete": not errors and not persistence_errors,
        },
    )
    return load_colored_api_period_model(current_date, days, supabase)


def _load_chunk(platform, start_date, end_date, credentials):
    cached = load_production_cache(platform, start_date, end_date)
    if cached is not None:
        return cached.data, cached.source
    result = load_production_data(
        platform, start_date, end_date, credentials=credentials
    )
    save_production_cache(
        platform, start_date, end_date, result.data, result.source
    )
    return result.data, result.source


def _date_chunks(start_date, end_date, chunk_days):
    chunks, cursor = [], start_date
    while cursor <= end_date:
        chunk_end = min(cursor + timedelta(days=int(chunk_days) - 1), end_date)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _model_from_persisted(rows, days):
    if rows is None or rows.empty:
        return pd.DataFrame(columns=["颜色", "尺码", "平台生产日均"])
    source = rows.copy()
    source["quantity"] = pd.to_numeric(
        source["quantity"], errors="coerce"
    ).fillna(0)
    model = source.groupby(
        ["color", "size"], as_index=False
    )["quantity"].sum()
    model["平台生产日均"] = model["quantity"] / int(days)
    return model.rename(columns={
        "color": "颜色", "size": "尺码",
    })[["颜色", "尺码", "平台生产日均"]]


def _errors_by_platform(errors):
    grouped = {}
    for key, message in dict(errors or {}).items():
        platform = str(key).split(":", 1)[0]
        grouped.setdefault(platform, []).append(str(message))
    return grouped


def _platform_state(
    platform, included, available, coverage, api_errors, persistence_errors,
):
    if platform in included:
        return "已读取（待保存）" if platform in persistence_errors else "已读取"
    if platform in available or int(coverage.get(platform, 0) or 0) > 0:
        return "部分读取"
    if platform in api_errors:
        return "读取失败"
    return "未开始"


def _platform_period(platform, model, included, available, coverage):
    days = int(coverage.get(platform, 0) or 0)
    if platform in included:
        return f"{model.start_date} 至 {model.end_date}"
    if platform in available or days:
        return f"已覆盖 {days} 天" if days else "已有部分数据"
    return "—"


def _platform_next_step(
    platform, included, available, coverage, api_errors, persistence_errors,
):
    persistence = " ".join(persistence_errors.get(platform, ())).lower()
    api = " ".join(api_errors.get(platform, ())).lower()
    combined = f"{persistence} {api}"
    if "replace_platform_daily_consumption" in combined or "pgrst20" in combined:
        return "先执行生产消耗模型 SQL，再保存已读取数据"
    if "30" in api and ("day" in api or "天" in api):
        return "接口只开放近 30 天；先使用可读区间，再补历史数据"
    if "rate" in api or "频繁" in api or "429" in api:
        return "平台限流，稍后重试未覆盖日期"
    if any(word in api for word in ("登录", "token", "auth", "凭据")):
        return "登录已过期，请管理员刷新平台授权"
    if "生产日期" in api or "production date" in api:
        return "平台有数据但缺生产日期，请核对日期字段映射"
    if platform in included:
        return "无需操作"
    if platform in available or int(coverage.get(platform, 0) or 0) > 0:
        return "继续读取尚未覆盖的日期"
    if platform in api_errors:
        message = api_errors[platform][0].strip()
        return message[:80] + ("…" if len(message) > 80 else "")
    return "点击上方按钮开始读取"
