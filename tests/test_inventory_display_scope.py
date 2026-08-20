import unittest

import pandas as pd

from ui.inventory.display_scope import (
    apply_routine_display_scope,
    routine_hidden_columns,
)


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


if __name__ == "__main__":
    unittest.main()
