import re

import pandas as pd

from utils.erp.parser import parse_normalized_production_data


COLUMNS = [
    "生产项编码", "生产单号", "材质", "商品", "商品底款编码", "商品底款",
    "颜色", "尺码", "数量", "生产项状态", "工艺路线", "生产批次",
    "运营商", "创建时间", "生产完成时间", "数据口径",
]


def parse_diy19_records(records, platform):
    rows = [_normalize_record(record, platform) for record in records]
    return parse_normalized_production_data(pd.DataFrame(rows, columns=COLUMNS))


def _normalize_record(record, platform):
    template_id = str(record.get("ProductTemplateID") or "")
    template_name = str(record.get("ProductTemplateName") or "").strip()
    color = str(record.get("ProductColorName") or "").strip()
    size = str(record.get("ProductSize") or "").strip()
    group_id = f"{platform}:{template_id}:{color}:{size}"
    product_name = _catalog_product_name(template_name, platform)
    created_at = record.get("StartDate")
    if record.get("StartDate") != record.get("EndDate"):
        created_at = None
    return {
        "生产项编码": group_id,
        "生产单号": template_id,
        "材质": _source_material(template_name),
        "商品": product_name,
        "商品底款编码": template_id,
        "商品底款": template_name,
        "颜色": color,
        "尺码": size,
        "数量": record.get("RecordCount") or 0,
        "生产项状态": "已生产",
        "工艺路线": _print_position(template_name),
        "生产批次": "",
        "运营商": platform,
        "创建时间": created_at,
        "生产完成时间": created_at,
        "数据口径": "汇总",
    }


def _catalog_product_name(name, platform):
    lowered = name.casefold()
    garment_words = ("t恤", "短袖", "卫衣", "hoodie", "t-shirt")
    if any(word in lowered for word in garment_words):
        return name
    if platform == "七创" and "cvc" in lowered:
        return f"T_SHIRT {name}"
    return name


def _source_material(name):
    if "铝板" in name:
        return "铝"
    if "冰箱贴" in name:
        return "软磁"
    cup_size = re.search(r"(\d+)\s*oz", name, re.IGNORECASE)
    if cup_size:
        return f"{cup_size.group(1)}oz"
    if "thin hoodie" in name.casefold():
        return "薄款"
    return name


def _print_position(name):
    if "双面" in name or "double" in name.casefold():
        return "双面"
    if "背面" in name or "back" in name.casefold():
        return "背面"
    return "正面"
