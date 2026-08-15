import pandas as pd

from utils.erp.parser import parse_normalized_production_data


NORMALIZED_COLUMNS = [
    "生产项编码", "生产单号", "材质", "商品", "商品底款编码", "商品底款",
    "颜色", "尺码", "数量", "生产项状态", "工艺路线", "生产批次",
    "运营商", "创建时间", "生产完成时间", "客户", "店铺",
]


def parse_fangguo_records(records):
    rows = [
        _normalize_record(record, index)
        for index, record in enumerate(records, start=1)
    ]
    source = pd.DataFrame(rows, columns=NORMALIZED_COLUMNS)
    return parse_normalized_production_data(source)


def _normalize_record(record, index):
    sku_name = str(record.get("skuName") or "").strip()
    product, color, size = _parse_sku_name(sku_name)
    produced_at = _production_date(record.get("date"))
    identity = ":".join(str(record.get(key) or "") for key in [
        "date", "shopId", "storeId", "skuName",
        "materialId", "colorId", "modelId", "giftId",
    ])
    return {
        "生产项编码": identity or f"fangguo-{index}",
        "生产单号": identity or f"fangguo-{index}",
        "材质": record.get("materialName") or product,
        "商品": sku_name or product,
        "商品底款编码": record.get("pictureCode") or "",
        "商品底款": sku_name,
        "颜色": record.get("colorName") or color,
        "尺码": record.get("modelName") or size,
        "数量": record.get("currentStatisticsNum") or 0,
        "生产项状态": "已生产",
        "工艺路线": product,
        "生产批次": "",
        "运营商": "方果",
        "创建时间": produced_at,
        "生产完成时间": produced_at,
        "客户": record.get("platformName") or "",
        "店铺": record.get("storeName") or record.get("shopName") or "",
    }


def _parse_sku_name(sku_name):
    parts = sku_name.split("-", 2)
    parts.extend([""] * (3 - len(parts)))
    return tuple(part.strip() for part in parts[:3])


def _production_date(value):
    if value in (None, ""):
        return ""
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return ""
    return (
        parsed.tz_convert("America/New_York")
        .normalize()
        .tz_localize(None)
    )
