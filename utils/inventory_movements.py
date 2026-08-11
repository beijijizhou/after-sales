STOCKTAKE_REASON_MARKER = "库存盘点设置"


def is_stocktake_reason(reason):
    return STOCKTAKE_REASON_MARKER in str(reason or "")


def movement_business_type(reason):
    return "库存设置" if is_stocktake_reason(reason) else ""
