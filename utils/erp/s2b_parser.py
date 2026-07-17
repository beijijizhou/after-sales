from io import BytesIO

import pandas as pd

from utils.erp.parser import parse_normalized_production_data


S2B_REQUIRED_COLUMNS = {
    "订单编码",
    "订单项编码",
    "选品信息",
    "颜色",
    "尺码",
    "订单件数",
    "订单状态",
    "生产时间",
}


def parse_s2b_workbook(file_bytes):
    source = pd.read_excel(BytesIO(file_bytes))
    missing = S2B_REQUIRED_COLUMNS - set(source.columns)
    if missing:
        raise ValueError(f"S2B Excel 缺少必要字段：{', '.join(sorted(missing))}")

    result = source.copy()
    result["生产项编码"] = result["订单项编码"]
    result["生产单号"] = result["订单编码"]
    result["商品"] = result["选品信息"]
    result["商品底款"] = result["选品信息"]
    result["数量"] = result["订单件数"]
    result["生产项状态"] = result["订单状态"]
    result["工艺路线"] = result["选品信息"]
    result["生产批次"] = result.get("生产批次号", "")
    result["创建时间"] = result["生产时间"]
    result["生产完成时间"] = result["生产时间"]
    result["运营商"] = "S2B"
    return parse_normalized_production_data(result)
