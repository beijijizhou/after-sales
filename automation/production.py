from dataclasses import dataclass

import pandas as pd

from automation.api.sds import fetch_sds_production_records
from automation.playwright.errors import ProductionLoginRequired
from automation.playwright.haloo import DIAGNOSTIC_PATH, ERP_PLATFORM_NAMES
from automation.playwright.haloo.workflow import download_production_workbook
from automation.playwright.s2b import download_s2b_workbook
from utils.erp import parse_platform_workbook
from utils.erp.sds_parser import parse_sds_records


SDS_PLATFORM_PROFILES = {
    "SDS1": "1号线",
    "SDS2": "2号线",
}
PRODUCTION_PLATFORM_NAMES = (
    *ERP_PLATFORM_NAMES,
    "S2B",
    *SDS_PLATFORM_PROFILES,
)
PRODUCTION_DEPARTMENTS = ("DTF", "3D", "UV")
PLATFORMS_BY_DEPARTMENT = {
    "DTF": PRODUCTION_PLATFORM_NAMES,
    "3D": (),
    "UV": ("SDS1", "SDS2"),
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
        )
        return ProductionDataResult(
            data=parse_sds_records(records, platform),
            source=f"{platform} API / {len(records):,} 条",
        )

    file_path = _download_workbook(
        platform,
        start_date,
        end_date,
        report_progress,
    )
    return ProductionDataResult(
        data=parse_platform_workbook(file_path.read_bytes(), platform),
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
