import unittest

import pandas as pd

from ui.inventory.sku.page import filter_sku_editor_source


class SkuEditorFilterTests(unittest.TestCase):
    def setUp(self):
        self.source = pd.DataFrame([
            {
                "sku_code": "SKU-1", "sku_name": "白色 L",
                "category": "黑白短袖", "brand": "caibbean",
                "material": "160g", "color": "白", "规格": "L",
            },
            {
                "sku_code": "SKU-2", "sku_name": "黑色 5XL",
                "category": "黑白短袖", "brand": "caibbean",
                "material": "160g", "color": "黑", "规格": "5XL",
            },
            {
                "sku_code": "PHONE-1", "sku_name": "iPhone 17",
                "category": "手机壳", "brand": "",
                "material": "iPhone", "color": "", "规格": "17",
            },
        ])

    def test_filters_by_color_and_size(self):
        result = filter_sku_editor_source(
            self.source,
            {"color": ["白"], "规格": ["L"]},
        )

        self.assertEqual(result["sku_code"].tolist(), ["SKU-1"])

    def test_uses_existing_brand_filter(self):
        by_brand = filter_sku_editor_source(
            self.source, {"brand": ["caibbean"]}
        )

        self.assertEqual(len(by_brand), 2)

    def test_phone_cases_are_hidden_by_default(self):
        result = filter_sku_editor_source(self.source)

        self.assertNotIn("PHONE-1", result["sku_code"].tolist())

    def test_explicit_phone_case_category_shows_phone_cases(self):
        result = filter_sku_editor_source(
            self.source, {"category": "手机壳"}
        )

        self.assertEqual(result["sku_code"].tolist(), ["PHONE-1"])


if __name__ == "__main__":
    unittest.main()
