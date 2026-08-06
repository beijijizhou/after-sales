import argparse
from datetime import date

import pandas as pd

from automation.production import (
    DTF_PRODUCTION_PLATFORMS,
    ProductionDataResult,
)
from automation.production_batch import (
    ALL_CLOTHING_PLATFORMS,
    BatchProductionResult,
    CLOTHING_CATEGORIES,
    load_all_clothing_production,
)
from automation.production_cache import (
    load_production_cache,
    save_production_cache,
)
from automation.sync.credentials import load_platform_credentials
from automation.sync.cache_seed import seed_daily_cache_from_period
from automation.sync.state import (
    is_complete,
    list_sync_status,
    lookback_dates,
    single_instance,
)


def sync_missing_days(lookback_days=7, target_date=None, force=False):
    dates = (
        [target_date]
        if target_date
        else lookback_dates(lookback_days)
    )
    results = []
    with single_instance():
        for index, day in enumerate(dates, start=1):
            print(
                f"[{index}/{len(dates)}] 检查 {day.isoformat()}",
                flush=True,
            )
            results.append(sync_production_day(day, force=force))
    return results


def sync_production_day(target_date, force=False):
    aggregate = load_production_cache(
        ALL_CLOTHING_PLATFORMS, target_date, target_date
    )
    if not force and is_complete(aggregate):
        print(
            f"  已有完整缓存，跳过（获取于 {aggregate.saved_at}）",
            flush=True,
        )
        return "skipped"
    if not force:
        seeded_rows = seed_daily_cache_from_period(target_date)
        if seeded_rows is not None:
            print(
                f"  已从完整区间缓存拆分，无需联网（{seeded_rows:,} 条）",
                flush=True,
            )
            return "derived"

    existing = {} if force else _load_platform_caches(target_date)
    missing = [
        platform for platform in DTF_PRODUCTION_PLATFORMS
        if platform not in existing
    ]
    print(
        "  需要获取：" + ("、".join(missing) if missing else "无"),
        flush=True,
    )
    credentials, credential_errors = _load_credentials(missing)
    if missing:
        batch = load_all_clothing_production(
            target_date,
            target_date,
            credentials,
            initial_errors=credential_errors,
            report_progress=lambda message: print(
                f"  {message}", flush=True
            ),
            platforms=missing,
            existing_results=existing,
        )
    else:
        batch = BatchProductionResult(
            _combine_existing(existing), existing, {}
        )
    for platform, result in batch.platform_results.items():
        save_production_cache(
            platform,
            target_date,
            target_date,
            result.data,
            result.source,
        )

    source = (
        f"{'部分数据 / ' if batch.errors else ''}"
        f"{len(batch.platform_results)} 个平台 / "
        f"{len(batch.data):,} 个衣服生产项"
    )
    save_production_cache(
        ALL_CLOTHING_PLATFORMS,
        target_date,
        target_date,
        batch.data,
        source,
        extra_metadata={
            "included_platforms": sorted(batch.platform_results),
            "missing_platforms": sorted(batch.errors),
            "platform_errors": {
                name: str(message) for name, message in batch.errors.items()
            },
            "is_complete": not batch.errors,
        },
    )
    if batch.errors:
        print(
            "  未完成：" + "；".join(
                f"{name}: {error}"
                for name, error in batch.errors.items()
            ),
            flush=True,
        )
        return "partial"
    print(f"  完成：{len(batch.data):,} 个衣服生产项", flush=True)
    return "completed"


def _load_platform_caches(target_date):
    results = {}
    for platform in DTF_PRODUCTION_PLATFORMS:
        cached = load_production_cache(
            platform, target_date, target_date
        )
        if cached is not None:
            results[platform] = ProductionDataResult(
                cached.data, cached.source
            )
    return results


def _combine_existing(results):
    frames = [
        result.data.loc[
            result.data["部门"].eq("DTF")
            & result.data["品类"].isin(CLOTHING_CATEGORIES)
        ].copy()
        for result in results.values()
    ]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _load_credentials(platforms):
    credentials, errors = {}, {}
    for platform in platforms:
        try:
            credentials[platform] = load_platform_credentials(platform)
        except Exception as error:
            errors[platform] = str(error)
    return credentials, errors


def _parse_args():
    parser = argparse.ArgumentParser(
        description="补齐本地每日生产数据缓存，不修改库存。"
    )
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--status", action="store_true")
    return parser.parse_args()


def main():
    arguments = _parse_args()
    if arguments.status:
        for row in list_sync_status(arguments.days):
            missing = "、".join(row["missing"])
            print(
                f"{row['date']}  {row['state']}  {row['saved_at']}"
                + (f"  缺少：{missing}" if missing else "")
            )
        return
    results = sync_missing_days(
        arguments.days, arguments.date, arguments.force
    )
    if "partial" in results:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
