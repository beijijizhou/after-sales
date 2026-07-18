import streamlit as st

from automation.api.diy19 import DIY19_BASE_URLS, load_diy19_credentials
from automation.api.fangguo import load_fangguo_credentials
from automation.api.hansen import load_hansen_credentials
from automation.api.sds import load_sds_credentials
from automation.production import (
    DIAGNOSTIC_PATH,
    PRODUCTION_PLATFORM_NAMES,
    ProductionLoginRequired,
    SDS_PLATFORM_PROFILES,
    load_production_data,
)
from automation.production_batch import (
    ALL_CLOTHING_PLATFORMS,
    load_all_clothing_production,
)


def fetch_and_store_production_data(
    platform,
    start_date,
    end_date,
    start_hour=0,
    end_hour=23,
):
    status = st.status("正在准备生产数据同步...", expanded=True)

    def report(message):
        status.write(message)

    try:
        if platform == ALL_CLOTHING_PLATFORMS:
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
            _store(platform, result.data, result.source)
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


def _fetch_all(start_date, end_date, start_hour, end_hour, report):
    credentials, credential_errors = {}, {}
    for platform in PRODUCTION_PLATFORM_NAMES:
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
    )
    for platform, result in batch.platform_results.items():
        _store(platform, result.data, result.source)
    source = (
        f"{len(batch.platform_results)} 个平台 / "
        f"{len(batch.data):,} 个衣服生产项"
    )
    _store(ALL_CLOTHING_PLATFORMS, batch.data, source)
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


def _store(platform, data, source):
    platform_data = dict(st.session_state.get("production_data_by_platform", {}))
    platform_data[platform] = {"data": data, "file": source}
    st.session_state["production_data_by_platform"] = platform_data
