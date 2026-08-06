import unittest

import pandas as pd

from ui.inventory.operations.adjustment_costs import (
    build_adjustment_cost_breakdown,
    build_size_cost_table,
    normalize_size_costs,
)


class InventoryAdjustmentCostTests(unittest.TestCase):
    def test_cost_editor_only_contains_sizes_with_quantity(self):
        quantities = pd.DataFrame([{
            "品类": "黑白短袖", "品牌": "Caribbean",
            "材质": "160g", "颜色": "黑",
            "S": 216, "M": 216, "L": 0,
        }])

        result = build_size_cost_table(quantities)

        self.assertEqual(result["尺码"].tolist(), ["S", "M"])
        self.assertEqual(result["数量"].tolist(), [216, 216])
        self.assertNotIn("L", result["尺码"].tolist())

    def test_long_cost_editor_normalizes_only_filled_prices(self):
        editor = pd.DataFrame([
            {"入库行": 1, "尺码": "S", "数量": 216, "成本": 1.38},
            {"入库行": 1, "尺码": "M", "数量": 216, "成本": None},
        ])

        result = normalize_size_costs(editor)

        self.assertEqual(result.to_dict("records"), [{
            "入库行": 1, "尺码": "S", "成本": 1.38,
        }])

    def test_breakdown_calculates_every_size_subtotal(self):
        quantities = pd.DataFrame([{
            "品类": "黑白短袖", "品牌": "Caribbean",
            "材质": "160g", "颜色": "黑",
            "S": 216, "M": 216,
        }])
        costs = pd.DataFrame([
            {"入库行": 1, "尺码": "S", "成本": 1.38},
            {"入库行": 1, "尺码": "M", "成本": 1.38},
        ])

        result = build_adjustment_cost_breakdown(quantities, costs)

        self.assertEqual(result["数量"].sum(), 432)
        self.assertAlmostEqual(result["小计"].sum(), 596.16)
        self.assertEqual(result["SKU"].nunique(), 1)

    def test_missing_size_cost_remains_missing_instead_of_zero(self):
        quantities = pd.DataFrame([{
            "品类": "黑白短袖", "品牌": "Caribbean",
            "材质": "160g", "颜色": "黑",
            "S": 216, "M": 216,
        }])
        costs = pd.DataFrame([
            {"入库行": 1, "尺码": "S", "成本": 1.38},
        ])

        result = build_adjustment_cost_breakdown(quantities, costs)

        missing = result[result["单价"].isna()]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing.iloc[0]["尺码"], "M")
        self.assertTrue(pd.isna(missing.iloc[0]["小计"]))


if __name__ == "__main__":
    unittest.main()
