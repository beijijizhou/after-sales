"""Shared manager-facing planning statuses."""


STATUS_NO_USAGE = "暂无系统消耗依据"
STATUS_LOW_STOCK = "当前库存偏低"
STATUS_STOCK_AVAILABLE = "当前库存可用"
STATUS_ARRIVED_PENDING = "已到柜待入库"
STATUS_DELAYED = "货柜已延迟"
STATUS_SHORTAGE_BEFORE_ARRIVAL = "到货前可能断货"
STATUS_DELAYED_ESTIMATE = "延期柜按明日估算"
STATUS_LOW_AFTER_ARRIVAL = "到货后库存仍偏低"
STATUS_COVERED_TO_ARRIVAL = "可撑到到货"


def classify_inventory_plan(
    *,
    has_arrivals,
    is_arrived,
    days_to_arrival,
    daily_usage,
    coverage_days,
    shortage,
    coverage_after_arrival,
    has_overdue_estimate=False,
    low_coverage_days=14,
):
    """Classify one planning result independently of its source category."""

    if not has_arrivals:
        if daily_usage <= 0:
            return STATUS_NO_USAGE
        if coverage_days < low_coverage_days:
            return STATUS_LOW_STOCK
        return STATUS_STOCK_AVAILABLE
    if is_arrived:
        return STATUS_ARRIVED_PENDING
    if days_to_arrival is not None and days_to_arrival < 0:
        return STATUS_DELAYED
    if daily_usage <= 0:
        return STATUS_NO_USAGE
    if shortage > 0:
        return STATUS_SHORTAGE_BEFORE_ARRIVAL
    if has_overdue_estimate:
        return STATUS_DELAYED_ESTIMATE
    if coverage_after_arrival < low_coverage_days:
        return STATUS_LOW_AFTER_ARRIVAL
    return STATUS_COVERED_TO_ARRIVAL
