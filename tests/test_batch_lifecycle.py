from datetime import date
import unittest
from unittest.mock import Mock, patch

from db.batches import (
    BatchKind,
    BatchReference,
    DailyOutboundReplacement,
    replace_batch,
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


if __name__ == "__main__":
    unittest.main()
