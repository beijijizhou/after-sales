import streamlit as st

from automation.production import (
    DTF_PRODUCTION_PLATFORMS,
    ProductionDataResult,
)
from automation.production_batch import ALL_CLOTHING_PLATFORMS
from automation.production_cache import (
    load_production_cache,
    save_production_cache,
)


def store_production_data(platform, data, source, saved_at=None):
    platform_data = dict(
        st.session_state.get("production_data_by_platform", {})
    )
    platform_data[platform] = {
        "data": data,
        "file": source,
        "saved_at": saved_at,
    }
    st.session_state["production_data_by_platform"] = platform_data


def sync_session_from_local_cache(
    platform, start_date, end_date, start_hour, end_hour
):
    cached = load_production_cache(
        platform, start_date, end_date, start_hour, end_hour
    )
    if cached is None:
        return
    current = st.session_state.get(
        "production_data_by_platform", {}
    ).get(platform, {})
    if current.get("saved_at") == cached.saved_at:
        return
    source = f"本地缓存 {cached.saved_at} / {cached.source}"
    store_production_data(
        platform, cached.data, source, cached.saved_at
    )


def save_cache_safely(
    platform, start_date, end_date, start_hour, end_hour,
    data, source, report, extra_metadata=None,
):
    try:
        saved_at = save_production_cache(
            platform,
            start_date,
            end_date,
            data,
            source,
            start_hour,
            end_hour,
            extra_metadata=extra_metadata,
        )
        report(f"{platform} 已保存到本地缓存：{saved_at}")
    except Exception as error:
        report(f"{platform} 本地缓存保存失败：{error}")


def aggregate_missing(platform, data, metadata):
    if platform != ALL_CLOTHING_PLATFORMS:
        return set()
    included = set(metadata.get("included_platforms") or [])
    if not included and "运营商" in data.columns:
        included = set(data["运营商"].dropna().astype(str))
    return (
        set(metadata.get("missing_platforms") or [])
        | (set(DTF_PRODUCTION_PLATFORMS) - included)
    )


def load_existing_platform_results(
    aggregate, missing, start_date, end_date, start_hour, end_hour
):
    results = {}
    included = set(DTF_PRODUCTION_PLATFORMS) - set(missing)
    for platform in included:
        cached = load_production_cache(
            platform, start_date, end_date, start_hour, end_hour
        )
        if cached is not None:
            results[platform] = ProductionDataResult(
                cached.data, cached.source
            )
            continue
        platform_df = aggregate.data[
            aggregate.data["运营商"].astype(str) == platform
        ].copy()
        results[platform] = ProductionDataResult(
            platform_df, f"原部分缓存 / {platform}"
        )
    return results
