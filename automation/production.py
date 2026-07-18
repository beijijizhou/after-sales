from dataclasses import dataclass

import pandas as pd

from automation.api.fangguo import fetch_fangguo_production_records
from automation.api.hansen import fetch_hansen_production_records
from automation.api.diy19 import DIY19_BASE_URLS, fetch_diy19_production_summary
from automation.api.sds import fetch_sds_production_records
from automation.playwright.errors import ProductionLoginRequired
from automation.playwright.haloo import DIAGNOSTIC_PATH, ERP_PLATFORM_NAMES
from automation.playwright.haloo.workflow import download_production_workbook
from automation.playwright.s2b import download_s2b_workbook
from utils.erp import parse_platform_workbook
from utils.erp.fangguo_parser import parse_fangguo_records
from utils.erp.hansen_parser import parse_hansen_records
from utils.erp.diy19_parser import parse_diy19_records
from utils.erp.sds_parser import parse_sds_records
from utils.erp.time_range import filter_production_time


SDS_PLATFORM_PROFILES = {
    "SDS1": "1号线",
    "SDS2": "2号线",
}
PRODUCTION_PLATFORM_NAMES = (
    *ERP_PLATFORM_NAMES,
    "S2B",
    "汉森",
    "七创",
    "一朵云",
    "方果",
    *SDS_PLATFORM_PROFILES,
)
PRODUCTION_DEPARTMENTS = ("DTF", "3D", "UV")
PLATFORMS_BY_DEPARTMENT = {
    "DTF": PRODUCTION_PLATFORM_NAMES,
    "3D": ("一朵云", "方果"),
    "UV": ("汉森", "一朵云", "方果", "SDS1", "SDS2"),
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
):
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
        data = filter_production_time(
            parse_sds_records(records, platform),
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
            start_hour,
            end_hour,
        )
        return ProductionDataResult(
            data=data,
            source=f"方果 API / {len(records):,} 单 / {len(data):,} 个生产项",
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

    file_path = _download_workbook(
        platform,
        start_date,
        end_date,
        report_progress,
    )
    data = filter_production_time(
        parse_platform_workbook(file_path.read_bytes(), platform),
        start_date,
        end_date,
        start_hour,
        end_hour,
    )
    return ProductionDataResult(
        data=data,
        source=file_path.name,
    )


def _download_workbook(platform, start_date, end_date, report_progress):
    if platform == "S2B":
        return download_s2b_workbook(
            start_date,
            end_date,
            report_progress,
        )
    return download_production_workbook(
        start_date,
        end_date,
        report_progress=report_progress,
        platform=platform,
    )


__all__ = [
    "DIAGNOSTIC_PATH",
    "PRODUCTION_PLATFORM_NAMES",
    "PRODUCTION_DEPARTMENTS",
    "PLATFORMS_BY_DEPARTMENT",
    "ProductionLoginRequired",
    "SDS_PLATFORM_PROFILES",
    "load_production_data",
]
