import unittest

import pandas as pd

from db.inventory.core.tables import build_inventory_table
from ui.inventory.display_scope import (
    apply_routine_display_scope,
    routine_hidden_columns,
)
from ui.inventory.stock.table_filters import render_inventory_table_filters


class InventoryDisplayScopeTests(unittest.TestCase):
    def test_uv_routine_views_hide_brand_and_color_only(self):
        source = pd.DataFrame([{
            "品类": "铁板画", "品牌": "内部品牌", "材质": "铁牌",
            "颜色": "白", "型号": "2030", "总库存": 6000,
        }])

        result = apply_routine_display_scope(source, "UV")

        self.assertEqual(
            result.columns.tolist(), ["品类", "材质", "型号", "总库存"]
        )
        self.assertEqual(routine_hidden_columns("UV"), {"品牌", "颜色"})
        self.assertIn("品牌", source.columns)

    def test_dtf_keeps_brand_and_color(self):
        source = pd.DataFrame([{"品牌": "Haloo", "颜色": "黑"}])

        result = apply_routine_display_scope(source, "DTF")

        self.assertEqual(result.columns.tolist(), ["品牌", "颜色"])

    def test_uv_color_variants_remain_visible_without_brand(self):
        source = pd.DataFrame([
            {"品类": "马克杯", "品牌": "", "材质": "11oz双彩杯", "颜色": color,
             "型号": "", "总库存": quantity}
            for color, quantity in [("黑", 8000), ("绿", 1200), ("红", 2000)]
        ])

        result = apply_routine_display_scope(source, "UV")

        self.assertEqual(
            result.columns.tolist(), ["品类", "材质", "颜色", "型号", "总库存"]
        )
        self.assertEqual(result["颜色"].tolist(), ["黑", "绿", "红"])

    def test_uv_single_color_stays_compact(self):
        source = pd.DataFrame([
            {"品类": "铁板画", "品牌": "", "材质": "铁牌", "颜色": "白",
             "型号": model, "总库存": 100}
            for model in ["2030", "1040"]
        ])

        self.assertNotIn("颜色", apply_routine_display_scope(source, "UV"))

    def test_configured_color_level_stays_visible_after_single_color_filter(self):
        source = pd.DataFrame([{
            "品类": "马克杯", "品牌": "", "材质": "11oz双彩杯",
            "颜色": "黑", "型号": "", "总库存": 7952,
        }])

        hidden = routine_hidden_columns(
            "UV", source,
            ("department", "category", "material", "color", "size"),
        )

        self.assertEqual(hidden, {"品牌"})

    def test_mug_inventory_table_keeps_each_color_identifiable(self):
        source = pd.DataFrame([
            {"category": "马克杯", "brand": "", "material": "11oz双彩杯",
             "color": color, "size": "", "quantity": quantity}
            for color, quantity in [("黑", 8000), ("绿", 1200), ("红", 2000)]
        ])
        table = build_inventory_table(source, category="马克杯", department="UV")
        visible = render_inventory_table_filters(table, [])

        self.assertEqual(routine_hidden_columns("UV", visible), {"品牌"})
        self.assertEqual(set(visible["颜色"]), {"黑", "绿", "红"})
        self.assertEqual(visible["总库存"].sum(), 11200)


if __name__ == "__main__":
    unittest.main()
