from datetime import date
import unittest
from unittest.mock import patch

import pandas as pd

from db.inventory.operations.outbound_audit import (
    build_daily_outbound_edit_rows,
    build_replacement_inventory,
    replace_daily_outbound_batch,
)


class DailyOutboundEditingTests(unittest.TestCase):
    def setUp(self):
        self.batch = pd.DataFrame([{
            "movement_date": date(2026, 8, 1),
            "brand": "Haloo", "material": "CVC",
            "color": "黑", "size": "XL",
            "quantity_change": -2520,
        }])

    def test_batch_is_converted_to_editable_outbound_rows(self):
        result = build_daily_outbound_edit_rows(self.batch)
        row = result.iloc[0]
        self.assertEqual(row["操作"], "扣减")
        self.assertEqual(row["数量"], 2520)
        self.assertEqual(row["备注"], "仓库每日出货")

    def test_database_date_string_becomes_editable_date(self):
        batch = self.batch.copy()
        batch.loc[0, "movement_date"] = "2026-08-01"

        result = build_daily_outbound_edit_rows(batch)

        self.assertEqual(result.iloc[0]["日期"], date(2026, 8, 1))
        self.assertIsInstance(result.iloc[0]["日期"], date)

    def test_precheck_adds_original_quantity_back_before_replacement(self):
        current = pd.DataFrame([{
            "brand": "Haloo", "material": "CVC",
            "color": "黑", "size": "XL", "quantity": 100,
        }])
        result = build_replacement_inventory(current, self.batch)
        self.assertEqual(result.iloc[0]["quantity"], 2620)

    @patch("db.inventory.operations.outbound_audit.apply_adjustment_rows")
    @patch("db.inventory.operations.outbound_audit.reverse_inventory_batch")
    def test_replace_reverses_original_then_writes_corrected_batch(
        self, reverse_batch, apply_rows,
    ):
        apply_rows.return_value = "replacement-id"
        replacement = build_daily_outbound_edit_rows(self.batch)
        replacement.loc[0, "数量"] = 2000

        result = replace_daily_outbound_batch(
            object(), "original-id", "DTF", "黑白短袖",
            self.batch, replacement, "Andy",
        )

        self.assertEqual(result, "replacement-id")
        reverse_batch.assert_called_once()
        apply_rows.assert_called_once()

    @patch("db.inventory.operations.outbound_audit.apply_adjustment_rows")
    @patch("db.inventory.operations.outbound_audit.reverse_inventory_batch")
    def test_failed_replacement_restores_original_outbound(
        self, reverse_batch, apply_rows,
    ):
        apply_rows.side_effect = [ValueError("save failed"), "restored-id"]
        replacement = build_daily_outbound_edit_rows(self.batch)

        with self.assertRaisesRegex(
            RuntimeError, "原出库数据已自动恢复"
        ):
            replace_daily_outbound_batch(
                object(), "original-id", "DTF", "黑白短袖",
                self.batch, replacement, "Andy",
            )

        reverse_batch.assert_called_once()
        self.assertEqual(apply_rows.call_count, 2)


if __name__ == "__main__":
    unittest.main()
