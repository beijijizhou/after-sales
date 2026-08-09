import unittest

import pandas as pd

from ui.inventory.operations.forms import adjustment_dimension_options
from ui.inventory.operations.adjustment_batch import (
    apply_adjustment_batch_fields,
)


class InventoryAdjustmentFormTests(unittest.TestCase):
    def test_one_batch_date_is_applied_to_every_adjustment_row(self):
        rows = pd.DataFrame([
            {"品牌": "Men's", "尺码": "M"},
            {"品牌": "Men's", "尺码": "3XL"},
        ])

        result = apply_adjustment_batch_fields(
            rows, pd.Timestamp("2026-08-09").date(), "扣减"
        )

        self.assertEqual(result["日期"].astype(str).tolist(), [
            "2026-08-09", "2026-08-09",
        ])
        self.assertEqual(result["操作"].tolist(), ["扣减", "扣减"])

    def test_temporary_transfer_lists_every_material_in_category_scope(self):
        inventory = pd.DataFrame([
            {"品牌": "Caribbean", "材质": "160g", "颜色": "白"},
            {"品牌": "Caribbean", "材质": "180g", "颜色": "白"},
            {"品牌": "Haloo", "材质": "CVC", "颜色": "黑"},
        ])

        brands, materials, colors = adjustment_dimension_options(inventory)

        self.assertEqual(materials, ["160g", "180g", "CVC"])
        self.assertEqual(brands, ["", "Caribbean", "Haloo"])
        self.assertEqual(colors, ["白", "黑"])


if __name__ == "__main__":
    unittest.main()
