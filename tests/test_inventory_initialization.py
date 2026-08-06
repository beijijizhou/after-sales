import unittest

import pandas as pd

from db.inventory.master_data.initialization import (
    find_uninitialized_skus,
)
from ui.inventory.sku.initialization import (
    build_initialization_signature,
    build_initialization_wide_source,
    expand_initialization_wide_rows,
    uses_standard_size_columns,
)


class InventoryInitializationTests(unittest.TestCase):
    def test_signature_accepts_numeric_and_missing_legacy_sku_codes(self):
        source = pd.DataFrame({"sku_code": ["SKU-1", 20002.0, None]})

        signature = build_initialization_signature(source)

        self.assertEqual(len(signature), 10)

    def test_standard_apparel_initialization_uses_wide_sizes(self):
        source = pd.DataFrame([
            {
                "category": "黑白短袖", "brand": "Cotton", "material": "160g",
                "color": "白", "unit": "件", "size": "S",
            },
            {
                "category": "黑白短袖", "brand": "Cotton", "material": "160g",
                "color": "白", "unit": "件", "size": "2XL",
            },
        ])

        self.assertTrue(uses_standard_size_columns(source))
        wide = build_initialization_wide_source(source)
        wide.loc[0, "2XL"] = 432
        expanded = expand_initialization_wide_rows(wide)
        selected = expanded[pd.to_numeric(expanded["初始库存"], errors="coerce") > 0]

        self.assertEqual(len(wide), 1)
        self.assertEqual(selected.iloc[0]["size"], "2XL")
        self.assertEqual(selected.iloc[0]["初始库存"], 432)

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
