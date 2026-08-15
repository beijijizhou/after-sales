from dataclasses import dataclass

import pandas as pd

from automation.api.fangguo import (
    fetch_fangguo_production_records,
    parse_fangguo_records,
)
from automation.api.hansen import (
    fetch_hansen_production_records,
    parse_hansen_records,
)
from automation.api.humbird import (
    fetch_humbird_production_records_http,
    fetch_open_production_records,
    parse_humbird_records,
)
from automation.api.diy19 import (
    DIY19_BASE_URLS,
    fetch_diy19_production_summary,
    parse_diy19_records,
)
from automation.api.sds import (
    fetch_sds_production_records,
    normalize_sds_platform_catalog,
    parse_sds_records,
)
from automation.api.s2b import (
    fetch_s2b_production_records,
    parse_s2b_production_records,
)
from automation.playwright.errors import ProductionLoginRequired
from automation.playwright.haloo import DIAGNOSTIC_PATH, ERP_PLATFORM_NAMES
from automation.playwright.haloo.workflow import download_production_workbook
from automation.playwright.s2b import download_s2b_workbook
from utils.erp import parse_platform_workbook
from utils.erp.time_range import filter_production_time


SDS_PLATFORM_PROFILES = {
    "SDS1": "1号线",
    "SDS2": "2号线",
    "忆点万象": "忆点万象",
    "3D热转印": "3D热转印",
}
DTF_PRODUCTION_PLATFORMS = (
    *ERP_PLATFORM_NAMES,
    "S2B",
    "汉森",
    "七创",
    "一朵云",
    "方果",
    "SDS1",
    "SDS2",
)
PRODUCTION_PLATFORM_NAMES = (
    *DTF_PRODUCTION_PLATFORMS,
    "忆点万象",
    "3D热转印",
)
PRODUCTION_DEPARTMENTS = ("DTF", "3D", "UV")
PLATFORMS_BY_DEPARTMENT = {
    "DTF": DTF_PRODUCTION_PLATFORMS,
    "3D": ("S2B", "3D热转印"),
    "UV": (
        "S2B", "汉森", "一朵云", "方果", "SDS1", "SDS2", "忆点万象",
    ),
}


@dataclass(frozen=True)
class ProductionDataResult:
    data: pd.DataFrame
    source: str


def load_production_data(
    platform,
    start_date,
    end_date,
    report_progress=None,
    credentials=None,
    start_hour=0,
    end_hour=23,
    account_name=None,
):
    if platform in ERP_PLATFORM_NAMES:
        if not credentials:
            raise ValueError(
                f"未配置 {platform} API token；不会启动浏览器读取"
            )
        if credentials.get("api_key"):
            try:
                records = fetch_open_production_records(
                    start_date, end_date, credentials, report_progress
                )
                api_source = "官方开放 API"
            except Exception as open_error:
                if not credentials.get("token"):
                    raise
                if report_progress:
                    report_progress(
                        "蜂鸟官方开放 API 暂不可用，"
                        "正在切换旧接口备用通道："
                        f"{open_error}"
                    )
                records = fetch_humbird_production_records_http(
                    platform,
                    start_date,
                    end_date,
                    credentials,
                    report_progress,
                )
                api_source = "旧接口备用通道"
        else:
            records = fetch_humbird_production_records_http(
                platform,
                start_date,
                end_date,
                credentials,
                report_progress,
            )
            api_source = "直接 API"
        data = filter_production_time(
            parse_humbird_records(records, platform),
            start_date,
            end_date,
            start_hour,
            end_hour,
        )
        return ProductionDataResult(
            data=data,
            source=f"{platform} {api_source} / {len(records):,} 条",
        )

    if platform in SDS_PLATFORM_PROFILES:
        if not credentials:
            profile = SDS_PLATFORM_PROFILES[platform]
            raise ValueError(
                f"未配置 {platform} 的 factory_credentials.{profile}"
            )
        records = fetch_sds_production_records(
            start_date,
            end_date,
            credentials,
            report_progress,
            platform,
            start_hour=start_hour,
            end_hour=end_hour,
        )
        data = parse_sds_records(records, platform)
        data = normalize_sds_platform_catalog(data, platform)
        data = filter_production_time(
            data,
            start_date,
            end_date,
            start_hour,
            end_hour,
        )
        return ProductionDataResult(
            data=data,
            source=f"{platform} API / {len(records):,} 条",
        )

    if platform == "汉森":
        if not credentials:
            raise ValueError("未配置汉森的 factory_credentials.汉森")
        records = fetch_hansen_production_records(
            start_date,
            end_date,
            credentials,
            report_progress,
        )
        data = filter_production_time(
            parse_hansen_records(records),
            start_date,
            end_date,
            start_hour,
            end_hour,
        )
        return ProductionDataResult(
            data=data,
            source=f"汉森 API / 筛选后 {len(data):,} 条",
        )

    if platform == "方果":
        if not credentials:
            raise ValueError("未配置方果的 factory_credentials.方果")
        records = fetch_fangguo_production_records(
            start_date,
            end_date,
            credentials,
            report_progress,
            start_hour=start_hour,
            end_hour=end_hour,
        )
        data = filter_production_time(
            parse_fangguo_records(records),
            start_date,
            end_date,
            0,
            23,
        )
        return ProductionDataResult(
            data=data,
            source=(
                f"方果生产统计 API / {len(records):,} 个 SKU 日期组合"
            ),
        )

    if platform in DIY19_BASE_URLS:
        if not credentials:
            raise ValueError(f"未配置{platform}的 factory_credentials.{platform}")
        records = fetch_diy19_production_summary(
            platform,
            start_date,
            end_date,
            credentials,
            report_progress,
            start_hour=start_hour,
            end_hour=end_hour,
        )
        data = filter_production_time(
            parse_diy19_records(records, platform),
            start_date,
            end_date,
            start_hour,
            end_hour,
        )
        return ProductionDataResult(
            data=data,
            source=f"{platform} API / {len(records):,} 个模板组合",
        )

    if platform == "S2B" and credentials:
        records = fetch_s2b_production_records(
            start_date,
            end_date,
            credentials,
            report_progress,
            start_hour=start_hour,
            end_hour=end_hour,
        )
        data = parse_s2b_production_records(records)
        if account_name:
            data["部门"] = str(account_name).upper()
        return ProductionDataResult(
            data=data,
            source=f"S2B {account_name or 'DTF'} 生产 API / {len(records):,} 条",
        )

    file_path = _download_workbook(
        platform,
        start_date,
        end_date,
        report_progress,
        account_name=account_name,
    )
    data = filter_production_time(
        parse_platform_workbook(file_path.read_bytes(), platform),
        start_date,
        end_date,
        start_hour,
        end_hour,
    )
    if platform == "S2B" and account_name:
        data["部门"] = str(account_name).upper()
    return ProductionDataResult(
        data=data,
        source=file_path.name,
    )


def _download_workbook(
    platform, start_date, end_date, report_progress, account_name=None
):
    if platform == "S2B":
        return download_s2b_workbook(
            start_date,
            end_date,
            report_progress,
            account_name=account_name or "DTF",
        )
    return download_production_workbook(
        start_date,
        end_date,
        report_progress=report_progress,
        platform=platform,
    )


def production_data_key(department, platform):
    account = str(department).upper()
    if platform == "S2B" and account != "DTF":
        return f"{account}::S2B"
    return platform


__all__ = [
    "DIAGNOSTIC_PATH",
    "DTF_PRODUCTION_PLATFORMS",
    "PRODUCTION_PLATFORM_NAMES",
    "PRODUCTION_DEPARTMENTS",
    "PLATFORMS_BY_DEPARTMENT",
    "production_data_key",
    "ProductionLoginRequired",
    "SDS_PLATFORM_PROFILES",
    "load_production_data",
]
