import unittest

import pandas as pd

from db.inventory.core.tables import build_inventory_table


class InventoryModelTableSortingTests(unittest.TestCase):
    def test_uv_inventory_places_recently_changed_skus_first(self):
        source = pd.DataFrame([
            {
                "category": "铁板画", "brand": "", "material": "铁牌",
                "color": "白", "size": "2030", "quantity": 6000,
                "updated_at": "2026-08-18T12:00:00+00:00",
            },
            {
                "category": "铁板画", "brand": "", "material": "铁牌",
                "color": "白", "size": "1040", "quantity": 9000,
                "updated_at": "2026-08-19T15:00:00+00:00",
            },
            {
                "category": "木板画", "brand": "", "material": "挂钟",
                "color": "白", "size": "25", "quantity": 8000,
                "updated_at": "2026-08-17T12:00:00+00:00",
            },
        ])

        result = build_inventory_table(
            source, category="", department="UV"
        )

        self.assertEqual(result["型号"].tolist(), ["1040", "2030", "25"])
        self.assertNotIn("_last_changed_at", result.columns)

    def test_uv_inventory_keeps_business_order_when_change_time_is_missing(self):
        source = pd.DataFrame([
            {
                "category": "铁板画", "brand": "", "material": "铁牌",
                "color": "白", "size": "3040", "quantity": 100,
            },
            {
                "category": "铁板画", "brand": "", "material": "铁牌",
                "color": "白", "size": "1040", "quantity": 100,
            },
        ])

        result = build_inventory_table(
            source, category="", department="UV"
        )

        self.assertEqual(result["型号"].tolist(), ["3040", "1040"])


if __name__ == "__main__":
    unittest.main()
