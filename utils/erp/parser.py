from io import BytesIO
import warnings

import pandas as pd

from utils.erp.catalog import normalize_production_catalog
from utils.erp.material import normalize_production_material


REQUIRED_COLUMNS = {
    "生产项编码", "生产单号", "商品", "商品底款", "颜色", "尺码",
    "数量", "生产项状态", "工艺路线", "创建时间", "生产完成时间",
}
TEXT_COLUMNS = [
    "生产项编码", "生产单号", "部门", "品类", "材质", "商品", "商品底款编码", "商品底款",
    "颜色", "尺码", "型号", "生产项状态", "工艺路线", "生产批次", "运营商", "数据口径",
]
SIZE_ALIASES = {"XXL": "2XL"}
COMPACT_ERP_COLUMNS = {
    "订单编码", "商品名称", "底款编码", "底款名称",
    "颜色", "尺码", "数量", "创建时间", "生产时间",
}


def parse_production_workbook(file_bytes, platform=None):
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="Workbook contains no default style"
        )
        source_df = pd.read_excel(BytesIO(file_bytes))
    if COMPACT_ERP_COLUMNS.issubset(source_df.columns):
        source_df = _expand_compact_erp_export(source_df, platform)
    elif platform:
        source_df["运营商"] = platform
    missing = REQUIRED_COLUMNS - set(source_df.columns)
    if missing:
        raise ValueError(f"缺少必要字段：{', '.join(sorted(missing))}")

    return parse_normalized_production_data(source_df)


def _expand_compact_erp_export(source_df, platform):
    result = source_df.rename(columns={
        "订单编码": "生产单号",
        "商品名称": "商品",
        "底款编码": "商品底款编码",
        "底款名称": "商品底款",
        "生产批次号": "生产批次",
        "生产时间": "生产完成时间",
    }).copy()
    identity_columns = [
        "生产单号", "商品底款编码", "颜色", "尺码", "生产批次",
    ]
    identity = result.reindex(columns=identity_columns, fill_value="")
    identity = identity.fillna("").astype(str).agg(":".join, axis=1)
    duplicate_index = identity.groupby(identity).cumcount().astype(str)
    result["生产项编码"] = identity + ":" + duplicate_index
    result["生产项状态"] = "已生产"
    result["工艺路线"] = result["商品"]
    result["运营商"] = platform or "Haloo"
    return result


def parse_normalized_production_data(source_df):
    result = source_df.copy()
    for column in TEXT_COLUMNS:
        if column in result.columns:
            result[column] = result[column].fillna("").astype(str).str.strip()
    result = normalize_production_catalog(result)
    result = normalize_production_material(result)
    result["尺码"] = result["尺码"].replace(SIZE_ALIASES)
    result["数量"] = pd.to_numeric(
        result["数量"], errors="coerce"
    ).fillna(0).clip(lower=0).astype(int)
    for column in ["创建时间", "生产完成时间", "开始时间"]:
        if column in result.columns:
            result[column] = pd.to_datetime(result[column], errors="coerce")
    return result[result["生产项编码"] != ""].reset_index(drop=True)
