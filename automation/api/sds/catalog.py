import re

from utils.erp.catalog import normalize_production_catalog
from utils.erp.inventory_mapping import normalize_uv_model


PLATFORM_DEPARTMENTS = {
    "忆点万象": "UV",
    "3D热转印": "3D",
}
DESCRIPTION_COLUMNS = ["品类", "商品", "商品底款", "工艺路线"]


def normalize_sds_platform_catalog(df, platform):
    department = PLATFORM_DEPARTMENTS.get(platform)
    if not department:
        return df
    result = df.copy()
    result["部门"] = department
    result = normalize_production_catalog(result)
    result["部门"] = department
    description = _description(result)
    if department == "UV":
        result["型号"] = [
            _infer_uv_model(current, text)
            for current, text in zip(result["型号"], description)
        ]
    else:
        result = _normalize_3d_categories(result, description)
    return result


def _normalize_3d_categories(df, description):
    result = df.copy()
    result["品类"] = "3D满复印"
    result.loc[description.str.contains("鼠标垫", regex=False), "品类"] = "鼠标垫"
    result.loc[description.str.contains("地垫", regex=False), "品类"] = "地垫"
    is_clothing = result["品类"] == "3D满复印"
    restore_size = (
        is_clothing
        & result["尺码"].fillna("").astype(str).str.strip().eq("")
        & ~result["型号"].fillna("").astype(str).str.strip().isin(
            ["", "未标注型号"]
        )
    )
    result.loc[restore_size, "尺码"] = result.loc[restore_size, "型号"]
    result.loc[is_clothing, "型号"] = ""
    return result


def _infer_uv_model(current, description):
    current = str(current or "").strip()
    if "圆形" in description or "圆铝" in description:
        return "YUAN"
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*[*x×]\s*(\d+(?:\.\d+)?)",
        description,
        flags=re.IGNORECASE,
    )
    if match:
        return normalize_uv_model(match.group(0))
    if current and current != "未标注型号":
        return normalize_uv_model(current)
    return current


def _description(df):
    columns = [column for column in DESCRIPTION_COLUMNS if column in df]
    return (
        df[columns].fillna("").astype(str).agg(" ".join, axis=1)
        .str.casefold()
    )
