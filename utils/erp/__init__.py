from utils.erp.parser import parse_production_workbook
from utils.erp.s2b_parser import parse_s2b_workbook
from utils.erp.summary import (
    apply_production_scope,
    build_color_size_summary,
    build_daily_summary,
    build_material_summary,
    build_status_summary,
)


def parse_platform_workbook(file_bytes, platform):
    if platform == "S2B":
        return parse_s2b_workbook(file_bytes)
    return parse_production_workbook(file_bytes)

__all__ = [
    "apply_production_scope",
    "build_color_size_summary",
    "build_daily_summary",
    "build_material_summary",
    "build_status_summary",
    "parse_production_workbook",
    "parse_platform_workbook",
]
