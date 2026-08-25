import pandas as pd

from utils.erp.hansen_styles import (
    find_hansen_hoodie_style,
    find_hansen_uv_style,
)


COLOR_ALIASES = {
    "black": "黑", "黑色": "黑", "white": "白", "白色": "白",
    "red": "红色", "orange": "橙色", "tangerine": "橙色",
    "橘色": "橙色", "yellow": "黄色", "golden": "黄色",
    "green": "绿色", "l": "绿色",
    "army green": "绿色", "mint green": "绿色",
    "blue": "蓝色", "sapphire blue": "蓝色", "aurora blue": "蓝色",
    "blue-green": "TiffanyBlue", "blue green": "TiffanyBlue",
    "bluegreen": "TiffanyBlue", "蓝绿色": "TiffanyBlue",
    "purple": "紫色", "light purple": "紫色",
    "pink": "粉色", "pale pink": "粉色", "light pink": "粉色",
    "粉红色": "粉色", "gray": "浅灰", "grey": "浅灰",
    "灰": "浅灰", "灰色": "浅灰", "light gray": "浅灰",
    "light grey": "浅灰", "浅灰": "浅灰", "浅灰色": "浅灰",
    "charcoal": "深灰", "dark gray": "深灰", "dark grey": "深灰",
    "深灰": "深灰", "深灰色": "深灰", "navy": "蓝色",
    "beige": "杏色",
    "apricot": "杏色", "brown": "棕色",
    "tiffany blue": "TiffanyBlue", "tiffanyblue": "TiffanyBlue",
}
DESCRIPTION_COLUMNS = ["品类", "商品", "商品底款", "工艺路线"]
HOODIE_PATTERN = r"卫衣|帽衫|hoodie|sweatshirt"
TSHIRT_PATTERN = r"短袖|男t|t恤|t-shirt|tshirt|t[_ ]shirt"
UV_PATTERN = r"挂钟|铁皮画|铁板画|铝牌画|铝板画|冰箱贴|保温杯|咖啡杯|马克杯"
THREED_PATTERN = r"鼠标垫|地垫|3d满复印|3d满印|3d服装"
UV_CATEGORY_RULES = {
    "挂钟": "挂钟",
    "铁皮画": "铁皮画",
    "铁板画": "铁皮画",
    "铁皮圆形": "铁皮画",
    "铁车牌": "铁皮画",
    "铝牌画": "铝牌画",
    "铝板画": "铝板画",
    "铝皮画": "铝牌画",
    "冰箱贴": "冰箱贴",
    "保温杯": "保温杯",
    "咖啡杯": "咖啡杯",
    "马克杯": "咖啡杯",
}
THREED_CATEGORY_RULES = {
    "鼠标垫": "鼠标垫",
    "地垫": "地垫",
    "3d满复印": "3D满复印",
    "3d满印": "3D满复印",
    "3d服装": "3D满复印",
}
DTF_CATEGORY_RULES = {
    "帆布袋": "帆布袋",
}
PENDING_TSHIRT_CATEGORY = "短袖版型待确认"
FEMALE_TSHIRT_PATTERN = r"女款|女士|women(?:'s)?|woman|female|ladies|lady"
CONFIRMED_ADULT_TSHIRT_RULES = (
    ("s2b", "180g女士大码烫画t恤"),
    ("隆丰", "美国-洛杉矶 女款圆领短袖t恤"),
)
GARMENT_CATEGORIES = {
    "黑白短袖", "彩色短袖", PENDING_TSHIRT_CATEGORY, "卫衣", "3D满复印",
}


def normalize_color(value):
    original = str(value or "").strip()
    lookup = original.casefold().rstrip(".").strip()
    if lookup in COLOR_ALIASES:
        return COLOR_ALIASES[lookup]
    if "(" in lookup:
        chinese_part = lookup.split("(", 1)[0].strip()
        english_part = lookup.split("(", 1)[1].split(")", 1)[0].strip()
        return COLOR_ALIASES.get(
            chinese_part,
            COLOR_ALIASES.get(english_part, original),
        )
    return original


def normalize_production_catalog(df):
    result = df.copy()
    result["颜色"] = result["颜色"].map(normalize_color)
    if "品类" not in result.columns:
        result["品类"] = ""
    if "部门" not in result.columns:
        result["部门"] = "DTF"
    if result.empty:
        return _split_size_and_model(result)

    columns = [column for column in DESCRIPTION_COLUMNS if column in result]
    description = result[columns].fillna("").astype(str).agg(" ".join, axis=1)
    description = description.str.casefold()
    result["部门"] = result["部门"].fillna("").astype(str).str.strip()
    result.loc[result["部门"] == "", "部门"] = "DTF"
    result.loc[description.str.contains(UV_PATTERN, regex=True), "部门"] = "UV"
    threed_matches = description.str.contains(THREED_PATTERN, regex=True)
    result.loc[threed_matches, "部门"] = "3D"
    for pattern, category in THREED_CATEGORY_RULES.items():
        matches = description.str.contains(pattern, regex=False)
        result.loc[matches, "品类"] = category
    for pattern, category in UV_CATEGORY_RULES.items():
        matches = description.str.contains(pattern, regex=False)
        result.loc[matches, "品类"] = category
    for pattern, category in DTF_CATEGORY_RULES.items():
        matches = description.str.contains(pattern, regex=False)
        result.loc[matches & (result["部门"] == "DTF"), "品类"] = category
    is_hoodie = description.str.contains(HOODIE_PATTERN, regex=True)
    if "运营商" in result.columns:
        is_hansen = result["运营商"].astype(str).str.casefold() == "汉森".casefold()
        hansen_hoodie = description.map(
            lambda value: find_hansen_hoodie_style(value) is not None
        )
        is_hoodie = is_hoodie | (is_hansen & hansen_hoodie)
        hansen_uv = description.map(
            lambda value: find_hansen_uv_style(value) is not None
        )
        result.loc[is_hansen & hansen_uv, "部门"] = "UV"
        result.loc[is_hansen & hansen_uv, "品类"] = "铁皮画"
    is_dtf = result["部门"] == "DTF"
    is_hoodie = is_hoodie & is_dtf
    is_tshirt = (
        is_dtf
        & ~is_hoodie
        & description.str.contains(TSHIRT_PATTERN, regex=True)
    )
    is_colored = ~result["颜色"].isin(["", "黑", "白"])

    result.loc[is_tshirt & ~is_colored, "品类"] = "黑白短袖"
    result.loc[is_tshirt & is_colored, "品类"] = "彩色短袖"
    product_title = result.get(
        "商品", pd.Series("", index=result.index)
    ).fillna("").astype(str).str.strip().str.casefold()
    platform = result.get(
        "运营商", pd.Series("", index=result.index)
    ).fillna("").astype(str).str.strip().str.casefold()
    female_labeled = product_title.str.contains(
        FEMALE_TSHIRT_PATTERN, regex=True
    )
    confirmed_adult = pd.Series(False, index=result.index)
    for confirmed_platform, title_pattern in CONFIRMED_ADULT_TSHIRT_RULES:
        confirmed_adult = confirmed_adult | (
            platform.eq(confirmed_platform)
            & product_title.str.contains(title_pattern, regex=False)
        )
    pending_audience = is_tshirt & female_labeled & ~confirmed_adult
    result["版型确认状态"] = ""
    result.loc[is_tshirt & confirmed_adult, "版型确认状态"] = (
        "已确认成人短袖"
    )
    result.loc[pending_audience, "版型确认状态"] = "待人工确认"
    result.loc[pending_audience, "品类"] = PENDING_TSHIRT_CATEGORY
    result.loc[is_hoodie, "品类"] = "卫衣"
    return _split_size_and_model(result)


def _split_size_and_model(df):
    result = df.copy()
    if "型号" not in result.columns:
        result["型号"] = ""
    if "尺码" not in result.columns:
        result["尺码"] = ""
    is_garment = result["品类"].isin(GARMENT_CATEGORIES)
    model_is_blank = result["型号"].fillna("").astype(str).str.strip() == ""
    move_to_model = ~is_garment & model_is_blank
    result.loc[move_to_model, "型号"] = result.loc[move_to_model, "尺码"]
    result.loc[~is_garment, "尺码"] = ""
    result.loc[
        ~is_garment
        & (result["型号"].fillna("").astype(str).str.strip() == ""),
        "型号",
    ] = "未标注型号"
    return result
