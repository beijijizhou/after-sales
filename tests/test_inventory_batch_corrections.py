import unittest

import pandas as pd

from db.inventory.operations.batch_corrections import (
    attach_batch_cost_lots,
    build_batch_correction_adjustments,
    build_batch_correction_editor,
    find_batch_cost_changes,
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

    def test_inbound_editor_uses_current_cost_lot_and_detects_price_change(self):
        editor = build_batch_correction_editor(self.movements)
        lots = pd.DataFrame([{
            "record_id": "lot-1", "brand": "杂牌", "material": "160g",
            "color": "白", "size": "S", "unit_cost": 1.4375,
        }])
        original = attach_batch_cost_lots(editor, lots)
        self.assertEqual(original.iloc[0]["成本批次ID"], "lot-1")
        self.assertEqual(original.iloc[0]["原单位成本"], 1.4375)
        self.assertEqual(original.iloc[0]["校准后成本"], 1.4375)

        edited = original.copy()
        edited.loc[0, "校准后成本"] = 1.5
        self.assertEqual(
            find_batch_cost_changes(original, edited), [("lot-1", 1.5)]
        )

    def test_quantity_correction_uses_revised_batch_cost(self):
        editor = build_batch_correction_editor(self.movements)
        editor["校准后成本"] = 1.5
        editor.loc[0, "校准后数量"] = 3000
        result = build_batch_correction_adjustments(
            self.movements, editor, "source-batch"
        )
        self.assertEqual(result.iloc[0]["成本"], 1.5)


if __name__ == "__main__":
    unittest.main()
