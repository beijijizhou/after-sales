import re

from utils.erp.hansen_styles import (
    find_hansen_hoodie_style,
    find_hansen_uv_style,
)


MATERIAL_COLUMNS = [
    "材质", "商品底款", "商品", "商品底款编码", "工艺路线", "运营商",
]
WEIGHT_PATTERN = re.compile(r"(?<!\d)(\d{2,4})\s*(?:g|克)", re.IGNORECASE)


def normalize_production_material(df):
    result = df.copy()
    if "材质" not in result.columns:
        result["材质"] = ""
    columns = [column for column in MATERIAL_COLUMNS if column in result]
    result["材质"] = result[columns].apply(_infer_material, axis=1)
    return result


def _infer_material(row):
    values = [str(value or "").strip() for value in row]
    descriptor = " ".join(value for value in values if value)
    lowered = descriptor.casefold()
    if "cvc" in lowered:
        return "CVC"
    weight = WEIGHT_PATTERN.search(descriptor)
    if weight:
        return f"{int(weight.group(1))}g"
    if "汉森" in descriptor:
        uv_style = find_hansen_uv_style(descriptor)
        if uv_style:
            return uv_style[1]
        hoodie_style = find_hansen_hoodie_style(descriptor)
        if hoodie_style:
            return hoodie_style[1]

    raw_material = values[0] if values else ""
    raw_lowered = raw_material.casefold()
    if raw_material:
        if "cotton" in raw_lowered:
            return "纯棉" if "100" in raw_lowered or "pure" in raw_lowered else "棉"
        return raw_material
    if "纯棉" in descriptor or "100% cotton" in lowered or "pure cotton" in lowered:
        return "纯棉"
    if "棉" in descriptor or "cotton" in lowered:
        return "棉"
    source_value = next((value for value in values[1:] if value), "")
    if source_value:
        return source_value
    return "未识别"
