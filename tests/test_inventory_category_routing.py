import unittest
import pandas as pd

from ui.inventory.category_routing import (
    exclude_consumable_dimensions,
    is_consumable_category,
)


class InventoryCategoryRoutingTests(unittest.TestCase):
    def test_dtf_consumable_labels_use_consumable_workflow(self):
        self.assertTrue(is_consumable_category("DTF耗材"))
        self.assertTrue(is_consumable_category("DTF 耗材"))

    def test_production_categories_keep_inventory_workflow(self):
        self.assertFalse(is_consumable_category("黑白短袖"))
        self.assertFalse(is_consumable_category("彩色短袖"))
        self.assertFalse(is_consumable_category("UV 铁板画"))

    def test_production_dimensions_exclude_consumable_categories(self):
        dimensions = pd.DataFrame([
            {"department": "DTF", "category": "黑白短袖"},
            {"department": "DTF", "category": "DTF耗材"},
            {"department": "UV", "category": "铁板画"},
        ])

        result = exclude_consumable_dimensions(dimensions)

        self.assertEqual(
            result["category"].tolist(), ["黑白短袖", "铁板画"]
        )


if __name__ == "__main__":
    unittest.main()
