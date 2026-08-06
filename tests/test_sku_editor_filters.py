import unittest

import pandas as pd

from ui.inventory.sku.page import (
    _display_catalog,
    build_sku_editor_wide_source,
    expand_sku_editor_wide_rows,
    filter_sku_editor_source,
    uses_standard_sku_sizes,
)


class SkuEditorFilterTests(unittest.TestCase):
    def test_apparel_editor_applies_one_wide_row_change_to_its_sizes(self):
        source = pd.DataFrame([
            {
                "id": "1", "sku_code": "SKU-1", "sku_name": "S",
                "category": "黑白短袖", "brand": "Cotton",
                "material": "160g", "color": "白", "规格": "S",
                "unit": "件", "quantity": 10, "is_active": True,
            },
            {
                "id": "2", "sku_code": "SKU-2", "sku_name": "2XL",
                "category": "黑白短袖", "brand": "Cotton",
                "material": "160g", "color": "白", "规格": "2XL",
                "unit": "件", "quantity": 20, "is_active": True,
            },
        ])

        self.assertTrue(uses_standard_sku_sizes(source))
        wide = build_sku_editor_wide_source(source)
        wide.loc[0, "brand"] = "Caribbean"
        expanded = expand_sku_editor_wide_rows(source, wide)

        self.assertEqual(len(wide), 1)
        self.assertEqual(wide.iloc[0]["S"], 10)
        self.assertEqual(wide.iloc[0]["2XL"], 20)
        self.assertEqual(set(expanded["brand"]), {"Caribbean"})
        self.assertEqual(set(expanded["id"]), {"1", "2"})

    def test_apparel_catalog_hides_internal_names_and_uses_wide_sizes(self):
        source = pd.DataFrame([
            {
                "sku_code": "SKU-1", "sku_name": "内部名称 S",
                "category": "黑白短袖", "brand": "Cotton",
                "material": "160g", "color": "白", "size": "S",
                "model": None, "unit": "件", "quantity": 10,
                "is_active": True,
            },
            {
                "sku_code": "SKU-2", "sku_name": "内部名称 2XL",
                "category": "黑白短袖", "brand": "Cotton",
                "material": "160g", "color": "白", "size": "2XL",
                "model": None, "unit": "件", "quantity": 20,
                "is_active": True,
            },
        ])

        display = _display_catalog(source)

        self.assertNotIn("SKU 编号", display.columns)
        self.assertNotIn("SKU 名称", display.columns)
        self.assertEqual(len(display), 1)
        self.assertEqual(display.iloc[0]["S"], 10)
        self.assertEqual(display.iloc[0]["2XL"], 20)

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
