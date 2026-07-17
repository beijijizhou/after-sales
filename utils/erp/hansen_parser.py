import pandas as pd

from utils.erp.parser import parse_normalized_production_data
from utils.erp.hansen_styles import (
    get_hansen_hoodie_style,
    get_hansen_uv_style,
)


NORMALIZED_COLUMNS = [
    "生产项编码", "生产单号", "材质", "商品", "商品底款编码", "商品底款",
    "颜色", "尺码", "数量", "生产项状态", "工艺路线", "生产批次",
    "运营商", "创建时间", "生产完成时间", "客户", "店铺",
]


def parse_hansen_records(records):
    rows = [_normalize_record(record) for record in records]
    source = pd.DataFrame(rows, columns=NORMALIZED_COLUMNS)
    return parse_normalized_production_data(source)


def _normalize_record(record):
    style_code = str(record.get("styleCode") or "").strip()
    category = str(record.get("category") or "").strip()
    sku = str(record.get("mappingSkuCode") or "").strip()
    hoodie_style = get_hansen_hoodie_style(style_code)
    uv_style = get_hansen_uv_style(style_code)
    mapped_style = hoodie_style or uv_style
    display_style = mapped_style[0] if mapped_style else style_code
    material = mapped_style[1] if mapped_style else style_code
    product_name = " ".join(
        value for value in [category, display_style] if value
    )
    created_at = record.get("createLabelTime")
    return {
        "生产项编码": record.get("labelNo") or record.get("id"),
        "生产单号": record.get("orderNo") or record.get("orderId"),
        "材质": material,
        "商品": product_name,
        "商品底款编码": style_code,
        "商品底款": sku or product_name,
        "颜色": record.get("colorName") or record.get("colorCode") or "",
        "尺码": record.get("sizeName") or record.get("sizeCode") or "",
        "数量": record.get("goodsTotalQty") or record.get("labelCount") or 0,
        "生产项状态": "已生产",
        "工艺路线": str(record.get("craftType") or ""),
        "生产批次": record.get("manufactureBatchNo") or "",
        "运营商": "汉森",
        "创建时间": created_at,
        "生产完成时间": created_at,
        "客户": record.get("customerName") or "",
        "店铺": record.get("shopName") or "",
    }
