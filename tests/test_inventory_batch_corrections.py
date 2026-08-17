import unittest

import pandas as pd

from db.inventory.operations.batch_corrections import (
    build_batch_correction_adjustments,
    build_batch_correction_editor,
)


class InventoryBatchCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.movements = pd.DataFrame([{
            "brand": "杂牌", "material": "160g", "color": "白",
            "size": "S", "quantity_change": 2520,
            "movement_date": "2026-08-16", "unit_cost": 1.25,
        }])

    def test_editor_uses_original_absolute_batch_quantity(self):
        editor = build_batch_correction_editor(self.movements)
        self.assertEqual(editor.iloc[0]["原批次数量"], 2520)
        self.assertEqual(editor.iloc[0]["校准后数量"], 2520)

    def test_inbound_correction_posts_only_positive_difference(self):
        editor = build_batch_correction_editor(self.movements)
        editor.loc[0, "校准后数量"] = 3850
        result = build_batch_correction_adjustments(
            self.movements, editor, "source-batch"
        )
        self.assertEqual(result.iloc[0]["操作"], "增加")
        self.assertEqual(result.iloc[0]["数量"], 1330)
        self.assertEqual(result.iloc[0]["成本"], 1.25)
        self.assertIn("2520→3850", result.iloc[0]["备注"])

    def test_outbound_correction_keeps_outbound_direction(self):
        movements = self.movements.assign(quantity_change=-2520)
        editor = build_batch_correction_editor(movements)
        editor.loc[0, "校准后数量"] = 3850
        result = build_batch_correction_adjustments(
            movements, editor, "source-batch"
        )
        self.assertEqual(result.iloc[0]["操作"], "扣减")
        self.assertEqual(result.iloc[0]["数量"], 1330)


if __name__ == "__main__":
    unittest.main()
