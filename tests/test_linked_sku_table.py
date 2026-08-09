import unittest

import pandas as pd

from ui.inventory.shared.linked_sku_table import linked_sku_options
from utils.auth.constants import NAV_ITEMS, NAV_SECTIONS, PAGE_ACCESS


class LinkedSkuTableTests(unittest.TestCase):
    def setUp(self):
        self.skus = pd.DataFrame([
            {
                "material": "180g", "brand": "Haloo",
                "color": "白", "size": "5XL",
            },
            {
                "material": "180g", "brand": "Haloo",
                "color": "白", "size": "S",
            },
            {
                "material": "180g", "brand": "Caribbean",
                "color": "黑", "size": "L",
            },
            {
                "material": "160g", "brand": "T64",
                "color": "白", "size": "M",
            },
            {
                "material": "CVC", "brand": "停用品牌",
                "color": "白", "size": "XL", "is_active": False,
            },
        ])

    def test_material_limits_brand_options(self):
        result = linked_sku_options(self.skus, material="180g")

        self.assertEqual(result["brands"], ["Caribbean", "Haloo"])
        self.assertNotIn("T64", result["brands"])

    def test_linked_sizes_use_business_order(self):
        result = linked_sku_options(
            self.skus, material="180g", brand="Haloo", color="白"
        )

        self.assertEqual(result["sizes"], ["S", "5XL"])

    def test_inactive_skus_are_excluded_from_linked_options(self):
        result = linked_sku_options(self.skus)

        self.assertNotIn("CVC", result["materials"])
        self.assertNotIn("停用品牌", result["brands"])

    def test_customer_sales_is_a_standalone_inventory_navigation_page(self):
        customer_sales = [item for item in NAV_ITEMS if item[0] == "customer_sales"]

        self.assertEqual(
            customer_sales,
            [("customer_sales", "客户销售出库", "pages/13_客户销售出库.py")],
        )
        self.assertEqual(PAGE_ACCESS["customer_sales"], "can_view_inventory")
        inventory_items = next(
            items for title, items in NAV_SECTIONS if title == "库存"
        )
        self.assertEqual(
            [item[0] for item in inventory_items][-2:],
            ["customer_sales", "sku_management"],
        )


if __name__ == "__main__":
    unittest.main()
