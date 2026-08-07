import unittest

import pandas as pd

from ui.inventory.operations.forms import adjustment_dimension_options


class InventoryAdjustmentFormTests(unittest.TestCase):
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
