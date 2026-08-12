from utils.daily_consumption import (
    ENTRY_MANUAL,
    ENTRY_SYSTEM,
    daily_consumption_source,
    is_daily_consumption_reason,
)
from utils.inventory_movements import is_stocktake_reason


def filter_history_batches(batch_df, mode):
    reasons = batch_df["备注"].fillna("").astype(str)
    shortage_artifacts = reasons.str.contains(
        "临时库存调整｜每日出库缺口补足", regex=False
    )
    daily_revision_artifacts = (
        batch_df["记录类别"].ne("库存表格记录")
        & reasons.str.contains("仓库每日出货", regex=False)
    )
    if mode == "daily_edit":
        return batch_df[shortage_artifacts | daily_revision_artifacts]
    normal_df = batch_df[
        batch_df["记录类别"].eq("库存表格记录")
        & ~shortage_artifacts
    ]
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
    is_temporary_adjustment = reasons.str.contains(
        "临时库存调整", regex=False
    )
    is_stocktake = reasons.map(is_stocktake_reason)
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
        "临时库存调整": is_temporary_adjustment,
        "库存设置": is_stocktake,
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


def filter_reversal_scope(batch_df, scope):
    if batch_df.empty or scope == "全部可撤销记录":
        return batch_df
    reasons = batch_df["备注"].fillna("").astype(str)
    directions = batch_df["类型"].fillna("").astype(str)
    sources = reasons.map(daily_consumption_source)
    masks = {
        "仓库每日出库": directions.eq("出库") & sources.eq(ENTRY_MANUAL),
        "系统库存扣减": directions.eq("出库") & sources.eq(ENTRY_SYSTEM),
        "临时库存调整": reasons.str.contains(
            "临时库存调整", regex=False
        ),
        "库存设置": reasons.map(is_stocktake_reason),
        "其他出入库": sources.eq("") & ~reasons.str.contains(
            "临时库存调整", regex=False
        ) & ~reasons.map(is_stocktake_reason),
    }
    mask = masks.get(scope)
    return batch_df if mask is None else batch_df[mask]
