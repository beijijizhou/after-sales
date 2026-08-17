from datetime import date
import unittest
from unittest.mock import Mock, patch

from db.batches import (
    BatchKind,
    BatchReference,
    ContainerInboundCorrection,
    DailyOutboundReplacement,
    InboundBatchKind,
    InboundBatchReference,
    InboundCostCorrection,
    InventoryQuantityCorrection,
    replace_batch,
    replace_inbound_batch,
    reverse_batch,
)


class BatchLifecycleTests(unittest.TestCase):
    def test_inventory_reference_requires_business_scope(self):
        with self.assertRaisesRegex(ValueError, "部门和品类"):
            BatchReference(BatchKind.INVENTORY, "batch-1")

    @patch("db.consumables.service.reverse_consumable_batch")
    def test_consumable_reversal_uses_domain_adapter(self, reverse):
        client = Mock()
        reverse.return_value = "reversal-1"

        result = reverse_batch(
            client,
            BatchReference(BatchKind.CONSUMABLE, "batch-1"),
            "Andy",
        )

        reverse.assert_called_once_with(client, "batch-1", "Andy")
        self.assertEqual(result, "reversal-1")

    @patch(
        "db.inventory.operations.daily_outbound_versions."
        "save_daily_outbound_revision"
    )
    def test_daily_outbound_replacement_creates_revision(self, save):
        client = Mock()
        rows = [{"品牌": "B64", "数量": 10}]
        replacement = DailyOutboundReplacement(
            date(2026, 8, 16), rows, "修正数量"
        )

        replace_batch(
            client,
            BatchReference(
                BatchKind.DAILY_OUTBOUND, "daily-1", "DTF", "黑白短袖"
            ),
            replacement,
            "Andy",
        )

        save.assert_called_once_with(
            client,
            "DTF",
            "黑白短袖",
            date(2026, 8, 16),
            rows,
            "Andy",
            daily_outbound_batch_id="daily-1",
            note="修正数量",
        )

    def test_non_replaceable_batch_rejects_update(self):
        with self.assertRaisesRegex(ValueError, "不支持修改替换"):
            replace_batch(
                Mock(),
                BatchReference(BatchKind.CONSUMABLE, "batch-1"),
                DailyOutboundReplacement(date.today(), []),
                "Andy",
            )

    @patch("db.inventory.operations.adjustments.apply_adjustment_rows")
    def test_inventory_inbound_correction_uses_one_entry_point(self, apply):
        client = Mock()
        rows = [{"操作": "增加", "数量": 5}]

        replace_inbound_batch(
            client,
            InboundBatchReference(
                InboundBatchKind.INVENTORY_MOVEMENT,
                "inbound-1",
                "DTF",
                "黑白短袖",
            ),
            InventoryQuantityCorrection(rows),
            "Andy",
        )

        apply.assert_called_once_with(
            client, "DTF", "黑白短袖", rows, "Andy", source_type="bulk"
        )

    @patch("db.inventory.container.costs.update_posted_container_item_costs")
    @patch("db.inventory.container.editor.correct_posted_container_quantities")
    def test_container_correction_combines_quantity_and_cost(
        self, correct_quantity, correct_cost,
    ):
        client = Mock()
        correct_quantity.return_value = {"rows": 1, "inventory_change": 5}
        correct_cost.return_value = {"rows": 1}

        result = replace_inbound_batch(
            client,
            InboundBatchReference(InboundBatchKind.CONTAINER, "container-1"),
            ContainerInboundCorrection(
                quantity_updates={"line-1": 10},
                item_costs={"line-1": 1.25},
            ),
            "Andy",
        )

        correct_quantity.assert_called_once_with(
            client, "container-1", {"line-1": 10}, "Andy"
        )
        correct_cost.assert_called_once_with(
            client, "container-1", {"line-1": 1.25}, "Andy"
        )
        self.assertEqual(result["quantity"]["inventory_change"], 5)

    @patch("db.finance.cost_maintenance.update_inbound_lot_cost")
    def test_inbound_cost_correction_uses_cost_adapter(self, update):
        client = Mock()

        replace_inbound_batch(
            client,
            InboundBatchReference(
                InboundBatchKind.INVENTORY_COST_LOT, "lot-1"
            ),
            InboundCostCorrection(1.25),
            "Andy",
        )

        update.assert_called_once_with(client, "lot-1", 1.25)


if __name__ == "__main__":
    unittest.main()
