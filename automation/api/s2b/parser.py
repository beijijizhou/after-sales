import pandas as pd

from utils.erp.parser import parse_normalized_production_data


def parse_s2b_production_records(records):
    source = pd.DataFrame(records)
    if source.empty:
        return parse_normalized_production_data(_empty_frame())
    required = {
        "order_code", "order_item_code", "basic_product_name",
        "color_name", "size_name", "num", "order_status_text",
        "production_at",
    }
    missing = required - set(source.columns)
    if missing:
        raise ValueError(
            "S2B 生产接口缺少字段：" + "、".join(sorted(missing))
        )
    result = pd.DataFrame({
        "生产项编码": source.get("id", source["order_item_code"]),
        "生产单号": source["order_code"],
        "商品": source["basic_product_name"],
        "商品底款": source["basic_product_name"],
        "颜色": source["color_name"],
        "尺码": source["size_name"],
        "数量": source["num"],
        "生产项状态": source["order_status_text"],
        "工艺路线": source["basic_product_name"],
        "生产批次": source.get("product_batch_number", ""),
        "创建时间": source["production_at"],
        "生产完成时间": source["production_at"],
        "运营商": "S2B",
        "数据口径": "S2B 账单生产时间（纽约）",
    })
    return parse_normalized_production_data(result)


def _empty_frame():
    return pd.DataFrame(columns=[
        "生产项编码", "生产单号", "商品", "商品底款", "颜色",
        "尺码", "数量", "生产项状态", "工艺路线", "生产批次",
        "创建时间", "生产完成时间", "运营商", "数据口径",
    ])
