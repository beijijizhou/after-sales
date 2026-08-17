"""Pure calculations shared by apparel, UV, and consumable planning."""

from dataclasses import dataclass
from datetime import date
import math
from typing import Iterable


@dataclass(frozen=True)
class StockPlan:
    """Current coverage and reorder result in an item's base unit."""

    estimated_current_quantity: float
    coverage_days: float | None
    target_quantity: float | None
    reorder_quantity: int
    reorder_packages: float | None


@dataclass(frozen=True)
class ArrivalPlan:
    """Inventory projection across every known incoming shipment."""

    days_to_first_arrival: int | None
    quantity_before_first_arrival: int
    shortage_before_arrivals: int
    quantity_after_all_arrivals: float
    coverage_after_all_arrivals: float | None


def calculate_stock_plan(
    current_quantity,
    daily_usage,
    *,
    target_days=None,
    minimum_quantity=0,
    elapsed_days=0,
    package_size=None,
):
    """Return one consistent stock and reorder calculation.

    Quantities are expressed in the caller's base unit. Packaging conversion
    is optional, so items measured only by pieces remain fully supported.
    """

    current = _number(current_quantity)
    usage = max(_number(daily_usage), 0.0)
    elapsed = max(int(elapsed_days or 0), 0)
    estimated = max(current - usage * elapsed, 0.0)
    coverage = estimated / usage if usage > 0 else None

    target = None
    reorder = 0
    if target_days is not None:
        days = max(int(target_days or 0), 0)
        target = max(usage * days, _number(minimum_quantity))
        reorder = max(round(target - estimated), 0)

    packages = None
    size = _number(package_size)
    if package_size is not None and size > 0:
        packages = round(reorder / size, 2)

    return StockPlan(
        estimated_current_quantity=estimated,
        coverage_days=coverage,
        target_quantity=target,
        reorder_quantity=int(reorder),
        reorder_packages=packages,
    )


def calculate_arrival_plan(
    current_quantity,
    daily_usage,
    arrival_events: Iterable[tuple[date, float]] | None,
    today: date,
):
    """Project stock through all incoming events and expose any interim gap."""

    current = _number(current_quantity)
    usage = max(_number(daily_usage), 0.0)
    events = sorted(
        (
            (arrival_date, _number(quantity))
            for arrival_date, quantity in (arrival_events or [])
            if arrival_date is not None
        ),
        key=lambda event: event[0],
    )

    if not events:
        return ArrivalPlan(
            days_to_first_arrival=None,
            quantity_before_first_arrival=max(math.floor(current), 0),
            shortage_before_arrivals=0,
            quantity_after_all_arrivals=max(current, 0.0),
            coverage_after_all_arrivals=(
                max(current, 0.0) / usage if usage > 0 else None
            ),
        )

    first_date = events[0][0]
    first_days = max((first_date - today).days, 0)
    before_first = max(math.floor(current - usage * first_days), 0)

    shortage = 0
    if usage > 0:
        for arrival_date in sorted({event[0] for event in events}):
            days = max((arrival_date - today).days, 0)
            prior_incoming = sum(
                quantity
                for previous_date, quantity in events
                if previous_date < arrival_date
            )
            stock_before = current - usage * days + prior_incoming
            shortage = max(shortage, math.ceil(max(-stock_before, 0)))

    last_date = events[-1][0]
    last_days = max((last_date - today).days, 0)
    after_all = max(
        current - usage * last_days + sum(quantity for _, quantity in events),
        0.0,
    )
    return ArrivalPlan(
        days_to_first_arrival=first_days,
        quantity_before_first_arrival=before_first,
        shortage_before_arrivals=shortage,
        quantity_after_all_arrivals=after_all,
        coverage_after_all_arrivals=(after_all / usage if usage > 0 else None),
    )


def _number(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return numeric if math.isfinite(numeric) else 0.0
