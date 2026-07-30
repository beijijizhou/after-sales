import unittest

import pandas as pd

from db.inventory.master_data.initialization import (
    find_uninitialized_skus,
)


class InventoryInitializationTests(unittest.TestCase):
    def test_only_zero_stock_without_inbound_history_is_pending(self):
        catalog = pd.DataFrame([
            _sku("new", "手机壳", 0),
            _sku("depleted", "手机壳", 0),
            _sku("stocked", "手机壳", 5),
            _sku("inactive", "手机壳", 0, active=False),
        ])
        movements = pd.DataFrame([
            {
                "category": "手机壳",
                "brand": "",
                "material": "",
                "color": "",
                "size": "depleted",
                "quantity_change": 10,
            }
        ])

        result = find_uninitialized_skus(catalog, movements)

        self.assertEqual(result["size"].tolist(), ["new"])

    def test_category_filter_is_applied(self):
        catalog = pd.DataFrame([
            _sku("15", "手机壳", 0),
            _sku("600ml", "保温杯", 0),
        ])

        result = find_uninitialized_skus(
            catalog, pd.DataFrame(), "手机壳"
        )

        self.assertEqual(result["category"].tolist(), ["手机壳"])


def _sku(size, category, quantity, active=True):
    return {
        "category": category,
        "brand": "",
        "material": "",
        "color": "",
        "size": size,
        "quantity": quantity,
        "is_active": active,
    }


if __name__ == "__main__":
    unittest.main()
