import unittest

import pandas as pd

from utils.sku_sorting import sort_sku_rows


class SkuSortingTests(unittest.TestCase):
    def test_material_color_and_apparel_size_use_business_order(self):
        source = pd.DataFrame([
            {"材质": "180g", "颜色": "粉色", "尺码/型号": "XL"},
            {"材质": "180g", "颜色": "粉色", "尺码/型号": "L"},
            {"材质": "180g", "颜色": "绿色", "尺码/型号": "2XL"},
            {"材质": "180g", "颜色": "粉色", "尺码/型号": "S"},
            {"材质": "160g", "颜色": "白色", "尺码/型号": "5XL"},
            {"材质": "180g", "颜色": "粉色", "尺码/型号": "M"},
        ])

        result = sort_sku_rows(source)

        self.assertEqual(result.iloc[0]["材质"], "160g")
        pink = result[
            (result["材质"] == "180g") & (result["颜色"] == "粉色")
        ]
        self.assertEqual(
            pink["尺码/型号"].tolist(), ["S", "M", "L", "XL"]
        )

    def test_unknown_models_follow_standard_apparel_sizes(self):
        source = pd.DataFrame([
            {"材质": "铁", "颜色": "白", "尺码/型号": "2030"},
            {"材质": "铁", "颜色": "白", "尺码/型号": "M"},
            {"材质": "铁", "颜色": "白", "尺码/型号": "1040"},
        ])

        result = sort_sku_rows(source)

        self.assertEqual(result["尺码/型号"].tolist(), ["M", "1040", "2030"])

    def test_supports_existing_uv_business_material_and_model_order(self):
        source = pd.DataFrame([
            {"材质": "铁牌", "颜色": "白", "型号": "1040"},
            {"材质": "铝牌", "颜色": "白", "型号": "2030"},
            {"材质": "铁牌", "颜色": "白", "型号": "YUAN"},
        ])

        result = sort_sku_rows(
            source,
            material="材质",
            color="颜色",
            size="型号",
            material_order={"铝牌": 0, "铁牌": 1},
            size_order=["2030", "3040", "1530", "YUAN", "1040"],
        )

        self.assertEqual(
            result[["材质", "型号"]].values.tolist(),
            [["铝牌", "2030"], ["铁牌", "YUAN"], ["铁牌", "1040"]],
        )


if __name__ == "__main__":
    unittest.main()
