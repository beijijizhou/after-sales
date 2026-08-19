"""One typed entry point for audited inbound-batch corrections."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class InboundBatchKind(StrEnum):
    INVENTORY_MOVEMENT = "inventory_movement"
    CONTAINER = "container"
    INVENTORY_COST_LOT = "inventory_cost_lot"
    CONSUMABLE_MOVEMENT = "consumable_movement"
    PENDING_COST = "pending_cost"


@dataclass(frozen=True)
class InboundBatchReference:
    kind: InboundBatchKind
    batch_id: str
    department: str | None = None
    category: str | None = None

    def __post_init__(self):
        if not str(self.batch_id).strip():
            raise ValueError("入库批次 ID 不能为空")
        if self.kind == InboundBatchKind.INVENTORY_MOVEMENT:
            if not self.department or not self.category:
                raise ValueError("库存入库批次必须提供部门和品类")


@dataclass(frozen=True)
class InventoryQuantityCorrection:
    adjustment_rows: Any


@dataclass(frozen=True)
class ContainerInboundCorrection:
    quantity_updates: Mapping[str, int] = field(default_factory=dict)
    item_costs: Mapping[str, float] = field(default_factory=dict)
    identity_updates: Mapping[str, Mapping[str, str]] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class InboundCostCorrection:
    unit_cost: float


def replace_inbound_batch(
    supabase,
    reference: InboundBatchReference,
    correction: (
        InventoryQuantityCorrection
        | ContainerInboundCorrection
        | InboundCostCorrection
    ),
    operated_by: str,
):
    """Validate and dispatch an inbound correction to its domain owner."""
    operator = str(operated_by or "").strip()
    if not operator:
        raise ValueError("入库批次操作人不能为空")

    if reference.kind == InboundBatchKind.INVENTORY_MOVEMENT:
        if not isinstance(correction, InventoryQuantityCorrection):
            raise TypeError("库存数量更正必须使用 InventoryQuantityCorrection")
        from db.inventory.operations.adjustments import apply_adjustment_rows

        return apply_adjustment_rows(
            supabase,
            reference.department,
            reference.category,
            correction.adjustment_rows,
            operator,
            source_type="bulk",
        )

    if reference.kind == InboundBatchKind.CONTAINER:
        if not isinstance(correction, ContainerInboundCorrection):
            raise TypeError("货柜入库更正必须使用 ContainerInboundCorrection")
        from db.inventory.container.costs import (
            update_posted_container_item_costs,
        )
        from db.inventory.container.editor import (
            correct_posted_container_identities,
            correct_posted_container_quantities,
        )

        identity_result = {
            "rows": 0, "inventory_change": 0, "unresolved_history": 0,
        }
        if correction.identity_updates:
            identity_result = correct_posted_container_identities(
                supabase, reference.batch_id,
                dict(correction.identity_updates), operator,
            )
        quantity_result = {
            "rows": 0, "inventory_change": 0, "unresolved_shortage": 0,
        }
        if correction.quantity_updates:
            quantity_result = correct_posted_container_quantities(
                supabase, reference.batch_id,
                dict(correction.quantity_updates), operator,
            )
        cost_result = {"rows": 0}
        if correction.item_costs:
            cost_result = update_posted_container_item_costs(
                supabase, reference.batch_id,
                dict(correction.item_costs), operator,
            )
        return {
            "identity": identity_result,
            "quantity": quantity_result,
            "cost": cost_result,
        }

    if not isinstance(correction, InboundCostCorrection):
        raise TypeError("入库成本更正必须使用 InboundCostCorrection")
    if reference.kind == InboundBatchKind.INVENTORY_COST_LOT:
        from db.finance.cost_maintenance import update_inbound_lot_cost

        return update_inbound_lot_cost(
            supabase, reference.batch_id, correction.unit_cost
        )
    if reference.kind == InboundBatchKind.CONSUMABLE_MOVEMENT:
        from db.finance.cost_maintenance import update_consumable_movement_cost

        return update_consumable_movement_cost(
            supabase, reference.batch_id, correction.unit_cost
        )
    if reference.kind == InboundBatchKind.PENDING_COST:
        from db.finance.pending_costs import update_pending_cost_batch

        return update_pending_cost_batch(
            supabase, reference.batch_id, correction.unit_cost
        )
    raise ValueError(f"不支持修改的入库批次类型：{reference.kind}")
