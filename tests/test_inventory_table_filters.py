import unittest

import pandas as pd

from ui.inventory.stock.table_filters import render_inventory_table_filters


class InventoryTableFilterTests(unittest.TestCase):
    def test_zero_stock_sku_rows_are_hidden_by_default(self):
        source = pd.DataFrame([
            {
                "品类": "黑白短袖", "品牌": "B64", "材质": "160g",
                "颜色": "白", "S": 0, "M": 0, "总库存": 0,
            },
            {
                "品类": "黑白短袖", "品牌": "B64", "材质": "160g",
                "颜色": "黑", "S": 10, "M": 0, "总库存": 10,
            },
        ])

        result = render_inventory_table_filters(source, ["S", "M"])

        self.assertEqual(result["颜色"].tolist(), ["黑"])

    def test_zero_stock_sku_rows_can_be_shown_for_review(self):
        source = pd.DataFrame([{
            "品类": "黑白短袖", "品牌": "B64", "材质": "160g",
            "颜色": "白", "S": 0, "M": 0, "总库存": 0,
        }])

        result = render_inventory_table_filters(
            source, ["S", "M"], include_zero_stock=True,
        )

        self.assertEqual(len(result), 1)

    def test_model_inventory_uses_total_stock_to_hide_zero_rows(self):
        source = pd.DataFrame([
            {
                "品类": "铁板画", "品牌": "铁牌", "材质": "铁牌",
                "颜色": "白", "型号": "2030", "总库存": 0,
            },
            {
                "品类": "铁板画", "品牌": "铁牌", "材质": "铁牌",
                "颜色": "白", "型号": "1040", "总库存": 20,
            },
        ])

        result = render_inventory_table_filters(source, [])

        self.assertEqual(result["型号"].tolist(), ["1040"])


if __name__ == "__main__":
    unittest.main()
