"""Shared commands for audited batch lifecycles.

Batch records are append-only business events.  A correction therefore means
creating a replacement revision, and a cancellation means creating a reversal
or void event; callers must never update or delete historical rows directly.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Iterable, Mapping


class BatchKind(StrEnum):
    INVENTORY = "inventory"
    DAILY_OUTBOUND = "daily_outbound"
    CONSUMABLE = "consumable"
    WAREHOUSE_TRANSFER = "warehouse_transfer"
    SALES_INVOICE = "sales_invoice"


@dataclass(frozen=True)
class BatchReference:
    kind: BatchKind
    batch_id: str
    department: str | None = None
    category: str | None = None

    def __post_init__(self):
        if not str(self.batch_id).strip():
            raise ValueError("批次 ID 不能为空")
        if self.kind in {BatchKind.INVENTORY, BatchKind.DAILY_OUTBOUND}:
            if not self.department or not self.category:
                raise ValueError("库存批次必须提供部门和品类")


@dataclass(frozen=True)
class DailyOutboundReplacement:
    movement_date: date
    rows: Iterable[Mapping[str, Any]]
    note: str | None = None


def reverse_batch(supabase, reference: BatchReference, operated_by: str):
    """Reverse or void a batch through its domain's atomic implementation."""
    operator = str(operated_by or "").strip()
    if not operator:
        raise ValueError("批次操作人不能为空")

    if reference.kind == BatchKind.INVENTORY:
        from db.inventory.operations.adjustments import reverse_inventory_batch

        return reverse_inventory_batch(
            supabase, reference.batch_id, reference.department,
            reference.category, operator,
        )
    if reference.kind == BatchKind.DAILY_OUTBOUND:
        from db.inventory.operations.daily_outbound_versions import (
            void_daily_outbound_revision,
        )

        return void_daily_outbound_revision(
            supabase, reference.batch_id, reference.department,
            reference.category, operator,
        )
    if reference.kind == BatchKind.CONSUMABLE:
        from db.consumables.service import reverse_consumable_batch

        return reverse_consumable_batch(supabase, reference.batch_id, operator)
    if reference.kind == BatchKind.WAREHOUSE_TRANSFER:
        from db.inventory.warehouses.repository import reverse_transfer

        return reverse_transfer(supabase, reference.batch_id, operator)
    if reference.kind == BatchKind.SALES_INVOICE:
        from db.inventory.sales.repository import void_sales_invoice

        return void_sales_invoice(supabase, reference.batch_id, operator)
    raise ValueError(f"不支持撤销的批次类型：{reference.kind}")


def replace_batch(
    supabase,
    reference: BatchReference,
    replacement: DailyOutboundReplacement,
    operated_by: str,
):
    """Create an audited replacement revision for a replaceable batch."""
    operator = str(operated_by or "").strip()
    if not operator:
        raise ValueError("批次操作人不能为空")
    if reference.kind != BatchKind.DAILY_OUTBOUND:
        raise ValueError(f"该批次类型暂不支持修改替换：{reference.kind}")
    if not isinstance(replacement, DailyOutboundReplacement):
        raise TypeError("每日出库替换必须使用 DailyOutboundReplacement")

    from db.inventory.operations.daily_outbound_versions import (
        save_daily_outbound_revision,
    )

    return save_daily_outbound_revision(
        supabase,
        reference.department,
        reference.category,
        replacement.movement_date,
        replacement.rows,
        operator,
        daily_outbound_batch_id=reference.batch_id,
        note=replacement.note,
    )
