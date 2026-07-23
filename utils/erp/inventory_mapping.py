import re

import pandas as pd

from utils.erp.catalog import normalize_production_catalog
from utils.erp.material import normalize_production_material


KEY_COLUMNS = ["department", "category", "planning_material", "color", "size"]

UV_CATEGORY_MAP = {
    "铁皮画": ("牌类", "铁牌"),
    "铁板画": ("牌类", "铁牌"),
    "铝板画": ("牌类", "铝牌"),
    "铝牌画": ("牌类", "铝牌"),
    "挂钟": ("木板画", "挂钟"),
}


def normalize_production_for_inventory(df):
    result = normalize_production_material(
        normalize_production_catalog(df)
    )
    result = result.copy()
    result["department"] = _text_column(result, "部门", "DTF")
    result["category"] = _text_column(result, "品类")
    result["material"] = _text_column(result, "材质")
    result["color"] = _text_column(result, "颜色")
    result["size"] = _text_column(result, "尺码").map(normalize_size)
    result["model"] = _text_column(result, "型号")
    result["quantity"] = pd.to_numeric(
        result.get("数量", 0), errors="coerce"
    ).fillna(0)

    is_uv = result["department"] == "UV"
    for source_category, (category, material) in UV_CATEGORY_MAP.items():
        matches = is_uv & (result["category"] == source_category)
        result.loc[matches, "category"] = category
        result.loc[matches, "material"] = material
    result.loc[is_uv, "size"] = result.loc[is_uv, "model"].map(
        normalize_uv_model
    )
    iron_only_models = result["size"].isin(["1040", "1530", "盾牌", "爱心"])
    result.loc[is_uv & iron_only_models, "category"] = "牌类"
    result.loc[is_uv & iron_only_models, "material"] = "铁牌"
    return add_planning_keys(result)


def normalize_inventory_for_planning(df, department=None):
    result = df.copy()
    defaults = {
        "department": department or "",
        "category": "",
        "brand": "",
        "material": "",
        "color": "",
        "size": "",
    }
    for column, default in defaults.items():
        result[column] = _text_column(result, column, default)
    return add_planning_keys(result)


def add_planning_keys(df):
    result = df.copy()
    is_dtf = result["department"] == "DTF"
    result["planning_material"] = result["material"]
    result.loc[is_dtf, "planning_material"] = "全部品牌/材质"
    result.loc[is_dtf, "brand"] = ""
    return result


def normalize_uv_model(value):
    original = str(value or "").strip()
    lowered = original.casefold()
    compact = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", lowered)
    numbers = [
        float(value) for value in re.findall(r"\d+(?:\.\d+)?", original)
    ]
    if "圆" in original:
        return "YUAN"
    if any(number == 2030 for number in numbers):
        return "2030"
    if any(number == 3040 for number in numbers):
        return "3040"
    if any(number == 1040 for number in numbers):
        return "1040"
    if any(number in {15.5, 30.5} for number in numbers):
        return "1530"
    if len(numbers) >= 2:
        dimensions = {round(numbers[0]), round(numbers[1])}
        if dimensions == {20, 30}:
            return "2030"
        if dimensions == {30, 40}:
            return "3040"
        if dimensions == {10, 40}:
            return "1040"
        if dimensions == {15, 30}:
            return "1530"
        if dimensions == {20}:
            return "YUAN"
        if dimensions == {25}:
            return "25"
    if compact in {"20", "2020"}:
        return "YUAN"
    if compact in {"25", "2525"}:
        return "25"
    if "shield" in lowered or "盾" in original:
        return "盾牌"
    if "heart" in lowered or "心" in original:
        return "爱心"
    return original or "未标注型号"


def normalize_size(value):
    original = str(value or "").strip()
    compact = re.sub(r"\s+", "", original.upper())
    numeric = re.search(r"([2-5])XL", compact)
    if numeric:
        return f"{numeric.group(1)}XL"
    x_size = re.search(r"(X{2,5})L", compact)
    if x_size:
        return f"{len(x_size.group(1))}XL"
    if re.search(r"XL", compact):
        return "XL"
    basic = re.match(r"([SML])(?:\(|$)", compact)
    return basic.group(1) if basic else original


def _text_column(df, column, default=""):
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype="object")
    values = df[column].fillna("").astype(str).str.strip()
    if default:
        values = values.mask(values == "", default)
    return values
