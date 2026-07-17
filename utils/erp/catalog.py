COLOR_ALIASES = {
    "black": "黑", "黑色": "黑", "white": "白", "白色": "白",
    "red": "红色", "orange": "橙色", "tangerine": "橙色",
    "橘色": "橙色", "yellow": "黄色", "green": "绿色",
    "army green": "绿色", "mint green": "绿色",
    "blue": "蓝色", "sapphire blue": "蓝色", "蓝绿色": "蓝色",
    "purple": "紫色", "light purple": "紫色",
    "pink": "粉色", "pale pink": "粉色", "light pink": "粉色",
    "粉红色": "粉色", "gray": "灰色", "grey": "灰色",
    "dark gray": "灰色", "dark grey": "灰色", "深灰色": "灰色",
    "浅灰": "灰色", "浅灰色": "灰色", "beige": "杏色",
    "apricot": "杏色", "brown": "棕色",
    "tiffany blue": "TiffanyBlue", "tiffanyblue": "TiffanyBlue",
}
DESCRIPTION_COLUMNS = ["品类", "商品", "商品底款", "工艺路线"]
HOODIE_PATTERN = r"卫衣|帽衫|hoodie|sweatshirt"
TSHIRT_PATTERN = r"短袖|t恤|t-shirt|tshirt"
UV_PATTERN = r"挂钟|铁皮画|铝牌画"
UV_CATEGORY_RULES = {
    "挂钟": "挂钟",
    "铁皮画": "铁皮画",
    "铝牌画": "铝牌画",
}


def normalize_color(value):
    original = str(value or "").strip()
    lookup = original.casefold().rstrip(".").strip()
    return COLOR_ALIASES.get(lookup, original)


def normalize_production_catalog(df):
    result = df.copy()
    result["颜色"] = result["颜色"].map(normalize_color)
    if "品类" not in result.columns:
        result["品类"] = ""

    columns = [column for column in DESCRIPTION_COLUMNS if column in result]
    description = result[columns].fillna("").astype(str).agg(" ".join, axis=1)
    description = description.str.casefold()
    if "部门" not in result.columns:
        result["部门"] = "DTF"
    result["部门"] = result["部门"].fillna("").astype(str).str.strip()
    result.loc[result["部门"] == "", "部门"] = "DTF"
    result.loc[description.str.contains(UV_PATTERN, regex=True), "部门"] = "UV"
    for pattern, category in UV_CATEGORY_RULES.items():
        matches = description.str.contains(pattern, regex=False)
        result.loc[matches, "品类"] = category

    is_hoodie = description.str.contains(HOODIE_PATTERN, regex=True)
    is_tshirt = ~is_hoodie & description.str.contains(TSHIRT_PATTERN, regex=True)
    is_colored = ~result["颜色"].isin(["", "黑", "白"])

    result.loc[is_tshirt & ~is_colored, "品类"] = "黑白短袖"
    result.loc[is_tshirt & is_colored, "品类"] = "彩色短袖"
    result.loc[is_hoodie, "品类"] = "卫衣"
    return result
