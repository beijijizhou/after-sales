import unittest

import pandas as pd

from ui.inventory.stock.table import build_sku_update_time_table


class InventorySkuUpdateTimeTests(unittest.TestCase):
    def test_apparel_update_times_are_wide_and_use_new_york_time(self):
        source = pd.DataFrame([
            {
                "category": "黑白短袖", "brand": "Men's",
                "material": "160g", "color": "白", "size": "M",
                "updated_at": "2026-08-08T03:47:01+00:00",
            },
            {
                "category": "黑白短袖", "brand": "Men's",
                "material": "160g", "color": "白", "size": "3XL",
                "updated_at": "2026-08-07T14:40:31+00:00",
            },
        ])

        result = build_sku_update_time_table(
            source, "DTF", ["M", "3XL"]
        )

        self.assertEqual(
            result.columns.tolist(),
            ["品类", "品牌", "材质", "颜色", "M", "3XL"],
        )
        self.assertEqual(result.loc[0, "M"], "2026-08-07 23:47")
        self.assertEqual(result.loc[0, "3XL"], "2026-08-07 10:40")


if __name__ == "__main__":
    unittest.main()
