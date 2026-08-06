from utils.daily_consumption import is_daily_consumption_reason


def filter_history_batches(batch_df, mode):
    normal_df = batch_df[batch_df["记录类别"] == "库存表格记录"]
    daily_mask = normal_df["备注"].fillna("").map(
        is_daily_consumption_reason
    )
    if mode == "daily":
        return normal_df[daily_mask]
    if mode == "regular":
        return normal_df[(normal_df["类型"] != "新增 SKU") & ~daily_mask]
    if mode == "sku":
        return normal_df[normal_df["类型"] == "新增 SKU"]
    return normal_df[normal_df["类型"] != "新增 SKU"]


def filter_batches_by_outbound_kind(batch_df, outbound_kind):
    if batch_df.empty or outbound_kind == "全部流水":
        return batch_df
    reasons = batch_df["备注"].fillna("").astype(str)
    is_outbound = batch_df["类型"].fillna("").astype(str) == "出库"
    is_container_inbound = (
        batch_df["类型"].fillna("").astype(str) == "入库"
    ) & reasons.str.contains("货柜入库：", regex=False)
    is_daily = reasons.map(is_daily_consumption_reason)
    is_legacy = (
        reasons.str.contains(
            "每日正常出货|每日出货|黑白短袖出库", regex=True
        )
        & ~is_daily
    )
    masks = {
        "货柜入库": is_container_inbound,
        "历史出库": is_outbound & is_legacy,
        "每日出库": is_outbound & is_daily,
        "每日库存扣减": is_outbound & is_daily,
        "每日消耗出库": is_outbound & is_daily,
        "临时出库": is_outbound & ~is_daily & ~is_legacy,
    }
    mask = masks.get(outbound_kind)
    return batch_df if mask is None else batch_df[mask]


def filter_batches_by_movement_type(batch_df, movement_types):
    if batch_df.empty or not movement_types:
        return batch_df
    return batch_df[
        batch_df["类型"].fillna("").apply(
            lambda value: any(
                movement_type in value for movement_type in movement_types
            )
        )
    ]
