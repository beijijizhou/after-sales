import pandas as pd

from utils.erp.parser import parse_normalized_production_data


NORMALIZED_COLUMNS = [
    "生产项编码",
    "生产单号",
    "品类",
    "商品",
    "商品底款编码",
    "商品底款",
    "颜色",
    "尺码",
    "数量",
    "生产项状态",
    "工艺路线",
    "生产批次",
    "运营商",
    "创建时间",
    "生产完成时间",
    "开始时间",
    "工厂",
]


def parse_sds_records(records, platform="SDS"):
    normalized = [_normalize_record(record, platform) for record in records]
    source = pd.DataFrame(normalized, columns=NORMALIZED_COLUMNS)
    return parse_normalized_production_data(source)


def _normalize_record(record, platform):
    product = record.get("product") or {}
    categories = product.get("categorys") or []
    category_path = " > ".join(
        str(item.get("name", "")).strip()
        for item in categories
        if item.get("name")
    )
    product_name = str(product.get("name") or "").strip()
    color = product.get("colorName") or ""
    source_category = category_path.split(" > ")[-1] if category_path else "其他"
    return {
        "生产项编码": record.get("no") or record.get("id"),
        "生产单号": record.get("merchantOrderNo") or record.get("no"),
        "品类": source_category,
        "商品": product_name,
        "商品底款编码": product.get("sku") or "",
        "商品底款": product_name,
        "颜色": color,
        "尺码": product.get("size") or "",
        "数量": record.get("num") or 0,
        "生产项状态": "已生产",
        "工艺路线": category_path,
        "生产批次": "",
        "运营商": platform,
        "创建时间": record.get("finishedDateTime"),
        "生产完成时间": record.get("finishedDateTime"),
        "开始时间": record.get("beginTime"),
        "工厂": record.get("factoryName") or "",
    }
