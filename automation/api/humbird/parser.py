import pandas as pd

from utils.erp.parser import parse_normalized_production_data


COLUMNS = [
    "生产项编码",
    "生产单号",
    "商品",
    "商品底款编码",
    "商品底款",
    "颜色",
    "尺码",
    "数量",
    "生产项状态",
    "工艺路线",
    "生产批次",
    "创建时间",
    "开始时间",
    "生产完成时间",
    "运营商",
]


def parse_humbird_records(records, platform):
    rows = [_normalize_record(record, platform) for record in records]
    source = pd.DataFrame(rows, columns=COLUMNS)
    return parse_normalized_production_data(source)


def _normalize_record(record, platform):
    return {
        "生产项编码": record.get("code"),
        "生产单号": record.get("production_order_id"),
        "商品": record.get("style_name"),
        "商品底款编码": record.get("blank_product_code"),
        "商品底款": record.get("blank_product_name"),
        "颜色": record.get("color"),
        "尺码": record.get("size"),
        "数量": record.get("qty"),
        "生产项状态": record.get("status_name"),
        "工艺路线": record.get("process_route_name"),
        "生产批次": record.get("production_batch_code"),
        "创建时间": _ny_datetime(record.get("created")),
        "开始时间": _ny_datetime(record.get("begin_production_time")),
        "生产完成时间": _ny_datetime(
            record.get("finish_production_time")
        ),
        "运营商": platform,
    }


def _ny_datetime(value):
    if value in (None, ""):
        return pd.NaT
    result = pd.to_datetime(value, unit="ms", utc=True, errors="coerce")
    if pd.isna(result):
        return pd.NaT
    return result.tz_convert("America/New_York").tz_localize(None)
