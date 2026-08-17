import unittest
from pathlib import Path

import pandas as pd

from ui.consumables.operations.stock_models import (
    build_stock_review_comparison,
    prepare_preview,
)
from ui.operations import prepare_stock_change_display


ROOT = Path(__file__).resolve().parents[1]


class StockReviewContractTests(unittest.TestCase):
    def test_positive_change_uses_inbound_label(self):
        display, operation = prepare_stock_change_display(pd.DataFrame([{
            "当前库存": 10, "本次变动": 3, "调整后库存": 13,
        }]))

        self.assertEqual(operation, "本次入库 (+)")
        self.assertIn(operation, display.columns)

    def test_negative_change_uses_outbound_label(self):
        display, operation = prepare_stock_change_display(pd.DataFrame([{
            "当前库存": 10, "本次变动": -3, "调整后库存": 7,
        }]))

        self.assertEqual(operation, "本次出库 (-)")
        self.assertIn(operation, display.columns)

    def test_mixed_change_uses_neutral_label(self):
        _, operation = prepare_stock_change_display(pd.DataFrame([
            {"当前库存": 10, "本次变动": -3, "调整后库存": 7},
            {"当前库存": 10, "本次变动": 2, "调整后库存": 12},
        ]))

        self.assertEqual(operation, "本次变动 (+/-)")

    def test_consumable_box_preview_adapts_to_shared_contract(self):
        comparison = build_stock_review_comparison(pd.DataFrame([{
            "耗材 SKU": "白墨", "当前库存（箱）": 5,
            "本次变动（箱）": -2, "操作后库存（箱）": 3,
        }]))
        display = prepare_preview(comparison, action="领用")

        self.assertEqual(comparison.loc[0, "当前库存"], 5)
        self.assertEqual(comparison.loc[0, "调整后库存"], 3)
        self.assertIn("本次出库 (-)", display.columns)

    def test_active_inventory_writers_share_one_renderer(self):
        inventory_source = (
            ROOT / "ui/inventory/operations/inventory_review.py"
        ).read_text()
        consumable_entry = (
            ROOT / "ui/consumables/operations/entry.py"
        ).read_text()
        consumable_tables = (
            ROOT / "ui/consumables/operations/stock_tables.py"
        ).read_text()

        for source in [inventory_source, consumable_entry, consumable_tables]:
            self.assertIn("render_stock_change_review", source)

    def test_reversible_ledgers_share_one_action_controller(self):
        paths = [
            "ui/inventory/history/workflows/reversal.py",
            "ui/consumables/operations/history.py",
            "ui/inventory/sales/history.py",
            "ui/inventory/transfers/processing.py",
        ]
        for path in paths:
            source = (ROOT / path).read_text()
            self.assertIn("render_batch_reversal_action", source)
            self.assertNotIn("reverse_batch(", source)

    def test_inventory_and_consumables_share_batch_state_contract(self):
        inventory_source = (
            ROOT / "ui/inventory/history/core/batch_selector.py"
        ).read_text()
        consumable_source = (
            ROOT / "ui/consumables/operations/history.py"
        ).read_text()

        for source in [inventory_source, consumable_source]:
            self.assertIn("synchronize_batch_selector_state", source)


if __name__ == "__main__":
    unittest.main()
