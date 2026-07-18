import pandas as pd

from utils.erp.parser import parse_normalized_production_data


NORMALIZED_COLUMNS = [
    "生产项编码", "生产单号", "材质", "商品", "商品底款编码", "商品底款",
    "颜色", "尺码", "数量", "生产项状态", "工艺路线", "生产批次",
    "运营商", "创建时间", "生产完成时间", "客户", "店铺",
]


def parse_fangguo_records(records):
    rows = []
    for order in records:
        items = order.get("tradeOrderItems") or []
        rows.extend(
            _normalize_item(order, item, index)
            for index, item in enumerate(items, start=1)
        )
    source = pd.DataFrame(rows, columns=NORMALIZED_COLUMNS)
    return parse_normalized_production_data(source)


def _normalize_item(order, item, index):
    factory_code = str(item.get("factoryCode") or "").strip()
    product, color, size = _parse_factory_code(factory_code)
    barcode = str(item.get("barcode") or "").strip()
    item_id = barcode or item.get("sysOid") or f"{order.get('id')}-{index}"
    created_at = _from_milliseconds(
        item.get("itemCreatedTime") or order.get("createTime")
    )
    return {
        "生产项编码": item_id,
        "生产单号": order.get("tid") or order.get("sysTid") or order.get("id"),
        "材质": product,
        "商品": product or item.get("title") or "",
        "商品底款编码": item.get("outerIid") or item.get("skuExtCode") or "",
        "商品底款": product,
        "颜色": color,
        "尺码": size or item.get("skuPropertiesName") or "",
        "数量": item.get("num") or 0,
        "生产项状态": order.get("outerOrderStatusDesc") or "",
        "工艺路线": product,
        "生产批次": item.get("batchNo") or "",
        "运营商": "方果",
        "创建时间": created_at,
        "生产完成时间": "",
        "客户": order.get("shopTenantName") or "",
        "店铺": order.get("shopName") or "",
    }


def _parse_factory_code(factory_code):
    parts = factory_code.split("-", 3)
    parts.extend([""] * (3 - len(parts)))
    return tuple(part.strip() for part in parts[:3])


def _from_milliseconds(value):
    if value in (None, ""):
        return ""
    return pd.to_datetime(value, unit="ms", utc=True).tz_convert(
        "America/New_York"
    ).tz_localize(None)
