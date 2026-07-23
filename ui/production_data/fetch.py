import streamlit as st

from automation.api.diy19 import DIY19_BASE_URLS, load_diy19_credentials
from automation.api.fangguo import load_fangguo_credentials
from automation.api.hansen import load_hansen_credentials
from automation.api.sds import load_sds_credentials
from automation.production import (
    DIAGNOSTIC_PATH,
    DTF_PRODUCTION_PLATFORMS,
    ProductionLoginRequired,
    SDS_PLATFORM_PROFILES,
    load_production_data,
)
from automation.production_batch import (
    ALL_CLOTHING_PLATFORMS,
    load_all_clothing_production,
)
from automation.production_cache import load_production_cache
from ui.production_data.cache_state import (
    aggregate_missing,
    load_existing_platform_results,
    save_cache_safely,
    store_production_data,
)


def fetch_and_store_production_data(
    platform,
    start_date,
    end_date,
    start_hour=0,
    end_hour=23,
    force_refresh=False,
):
    status = st.status("正在准备生产数据同步...", expanded=True)

    def report(message):
        status.write(message)

    try:
        cached = None if force_refresh else load_production_cache(
            platform, start_date, end_date, start_hour, end_hour
        )
        if cached is not None:
            missing = aggregate_missing(
                platform, cached.data, cached.metadata
            )
            if missing:
                report(
                    "检测到部分缓存，仅重新获取："
                    + "、".join(sorted(missing))
                )
                existing = load_existing_platform_results(
                    cached, missing, start_date, end_date,
                    start_hour, end_hour,
                )
                source, errors = _fetch_all(
                    start_date, end_date, start_hour, end_hour, report,
                    platforms=missing,
                    existing_results=existing,
                )
            else:
                source = f"本地缓存 {cached.saved_at} / {cached.source}"
                store_production_data(
                    platform, cached.data, source, cached.saved_at
                )
                status.update(
                    label=f"已从本地缓存读取：{cached.saved_at}",
                    state="complete",
                    expanded=False,
                )
                st.toast("已读取本地缓存")
                return
        elif platform == ALL_CLOTHING_PLATFORMS:
            source, errors = _fetch_all(
                start_date, end_date, start_hour, end_hour, report
            )
        else:
            result = load_production_data(
                platform,
                start_date,
                end_date,
                report_progress=report,
                credentials=_credentials_for(platform),
                start_hour=start_hour,
                end_hour=end_hour,
            )
            store_production_data(platform, result.data, result.source)
            save_cache_safely(
                platform,
                start_date,
                end_date,
                start_hour,
                end_hour,
                result.data,
                result.source,
                report,
            )
            source, errors = result.source, {}
        status.update(
            label=f"生产数据获取完成：{source}",
            state="complete",
            expanded=False,
        )
        st.toast("生产数据获取完成")
        if errors:
            failed = "、".join(errors)
            st.warning(f"以下平台未获取成功：{failed}")
            with st.expander("查看失败原因"):
                st.dataframe(
                    [
                        {"平台": name, "失败原因": message}
                        for name, message in errors.items()
                    ],
                    hide_index=True,
                    width="stretch",
                )
    except ProductionLoginRequired as error:
        status.update(label=f"等待登录：{error}", state="error", expanded=True)
        st.warning(str(error))
    except Exception as error:
        status.update(label=f"获取失败：{error}", state="error", expanded=True)
        st.error(f"生产数据获取失败：{error}")
        if DIAGNOSTIC_PATH.exists():
            st.caption("已记录当前页面控件，便于校准自动化流程。")


def _fetch_all(
    start_date, end_date, start_hour, end_hour, report,
    platforms=None, existing_results=None,
):
    credentials, credential_errors = {}, {}
    requested = tuple(platforms or DTF_PRODUCTION_PLATFORMS)
    for platform in requested:
        try:
            credentials[platform] = _credentials_for(platform)
        except Exception as error:
            credential_errors[platform] = str(error)
    batch = load_all_clothing_production(
        start_date,
        end_date,
        credentials,
        initial_errors=credential_errors,
        report_progress=report,
        start_hour=start_hour,
        end_hour=end_hour,
        platforms=requested,
        existing_results=existing_results,
    )
    for platform, result in batch.platform_results.items():
        store_production_data(platform, result.data, result.source)
        save_cache_safely(
            platform,
            start_date,
            end_date,
            start_hour,
            end_hour,
            result.data,
            result.source,
            report,
        )
    source = (
        f"{'部分数据 / ' if batch.errors else ''}"
        f"{len(batch.platform_results)} 个平台 / "
        f"{len(batch.data):,} 个衣服生产项"
    )
    store_production_data(ALL_CLOTHING_PLATFORMS, batch.data, source)
    save_cache_safely(
        ALL_CLOTHING_PLATFORMS,
        start_date,
        end_date,
        start_hour,
        end_hour,
        batch.data,
        source,
        report,
        extra_metadata={
            "included_platforms": sorted(batch.platform_results),
            "missing_platforms": sorted(batch.errors),
            "is_complete": not batch.errors,
        },
    )
    return source, batch.errors


def _credentials_for(platform):
    if platform in SDS_PLATFORM_PROFILES:
        return load_sds_credentials(
            st.secrets, SDS_PLATFORM_PROFILES[platform]
        )
    if platform == "汉森":
        return load_hansen_credentials(st.secrets)
    if platform == "方果":
        return load_fangguo_credentials(st.secrets)
    if platform in DIY19_BASE_URLS:
        return load_diy19_credentials(st.secrets, platform)
    return None
