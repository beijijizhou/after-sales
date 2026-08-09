import unittest

import pandas as pd

from db.inventory import SIZE_COLUMNS
from ui.inventory.operations.adjustment_preview import (
    build_adjustment_stock_comparison,
    build_inventory_change_comparison,
)


class InventoryAdjustmentPreviewTests(unittest.TestCase):
    def test_normalized_daily_outbound_uses_shared_three_stage_review(self):
        inventory = pd.DataFrame([{
            "brand": "Men's", "material": "160g", "color": "白",
            "size": "3XL", "quantity": 500,
        }])
        outbound = pd.DataFrame([{
            "操作": "扣减", "品牌": "Men's", "材质": "160g",
            "颜色": "白", "尺码": "3XL", "数量": 30,
        }])

        result = build_inventory_change_comparison(inventory, outbound)

        self.assertEqual(result.iloc[0]["当前库存"], 500)
        self.assertEqual(result.iloc[0]["本次变动"], -30)
        self.assertEqual(result.iloc[0]["调整后库存"], 470)

    def test_container_inbound_keeps_department_and_category_scope(self):
        inventory = pd.DataFrame([{
            "department": "UV", "category": "铁板画", "brand": "",
            "material": "铁牌", "color": "白", "size": "2030",
            "quantity": 1000,
        }])
        inbound = pd.DataFrame([{
            "department": "UV", "category": "铁板画", "brand": "",
            "material": "铁牌", "color": "白", "size": "2030",
            "quantity": 220, "操作": "增加",
        }])

        result = build_inventory_change_comparison(inventory, inbound)

        self.assertEqual(result.iloc[0]["部门"], "UV")
        self.assertEqual(result.iloc[0]["品类"], "铁板画")
        self.assertEqual(result.iloc[0]["本次变动"], 220)
        self.assertEqual(result.iloc[0]["调整后库存"], 1220)

    def test_inbound_shows_current_change_and_result(self):
        inventory = pd.DataFrame([{
            "品牌": "", "材质": "180g", "颜色": "粉色",
            **{size: 0 for size in SIZE_COLUMNS},
            "S": 100, "M": 200,
        }])
        edited = pd.DataFrame([{
            "品牌": "", "材质": "180g", "颜色": "粉色",
            **{size: 0 for size in SIZE_COLUMNS},
            "S": 10, "M": 20,
        }])

        result = build_adjustment_stock_comparison(
            inventory, edited, "增加"
        )

        self.assertEqual(
            result["尺码"].tolist(),
            ["S", "M"],
        )
        self.assertEqual(result.iloc[0]["当前库存"], 100)
        self.assertEqual(result.iloc[0]["本次变动"], 10)
        self.assertEqual(result.iloc[0]["调整后库存"], 110)
        self.assertEqual(result.iloc[1]["调整后库存"], 220)

    def test_outbound_uses_negative_change_and_exposes_negative_result(self):
        inventory = pd.DataFrame([{
            "品牌": "Caribbean", "材质": "160g", "颜色": "黑",
            **{size: 0 for size in SIZE_COLUMNS},
            "L": 50,
        }])
        edited = pd.DataFrame([{
            "品牌": "Caribbean", "材质": "160g", "颜色": "黑",
            **{size: 0 for size in SIZE_COLUMNS},
            "L": 60,
        }])

        result = build_adjustment_stock_comparison(
            inventory, edited, "扣减"
        )

        self.assertEqual(result.iloc[0]["尺码"], "L")
        self.assertEqual(result.iloc[0]["当前库存"], 50)
        self.assertEqual(result.iloc[0]["本次变动"], -60)
        self.assertEqual(result.iloc[0]["调整后库存"], -10)

    def test_long_preview_uses_material_brand_color_size_order(self):
        inventory = pd.DataFrame([
            {
                "品牌": "Men's", "材质": "160g", "颜色": "白",
                **{size: 100 for size in SIZE_COLUMNS},
            },
            {
                "品牌": "Brand A", "材质": "160g", "颜色": "黑",
                **{size: 100 for size in SIZE_COLUMNS},
            },
        ])
        edited = pd.DataFrame([
            {
                "品牌": "Men's", "材质": "160g", "颜色": "白",
                **{size: 0 for size in SIZE_COLUMNS}, "3XL": 30, "S": 10,
            },
            {
                "品牌": "Brand A", "材质": "160g", "颜色": "黑",
                **{size: 0 for size in SIZE_COLUMNS}, "M": 20,
            },
        ])

        result = build_adjustment_stock_comparison(inventory, edited, "扣减")

        self.assertEqual(
            list(result[["材质", "品牌", "颜色", "尺码"]].itertuples(
                index=False, name=None
            )),
            [
                ("160g", "Brand A", "黑", "M"),
                ("160g", "Men's", "白", "S"),
                ("160g", "Men's", "白", "3XL"),
            ],
        )

    def test_model_inventory_uses_the_same_comparison(self):
        inventory = pd.DataFrame([{
            "品牌": "", "材质": "铁牌", "颜色": "白",
            "型号": "2030", "总库存": 5000,
        }])
        edited = pd.DataFrame([{
            "品牌": "", "材质": "铁牌", "颜色": "白",
            "型号": "2030", "数量": 2000,
        }])

        result = build_adjustment_stock_comparison(inventory, edited, "扣减")

        self.assertEqual(result.iloc[0]["尺码"], "2030")
        self.assertEqual(result.iloc[0]["当前库存"], 5000)
        self.assertEqual(result.iloc[0]["本次变动"], -2000)
        self.assertEqual(result.iloc[0]["调整后库存"], 3000)


if __name__ == "__main__":
    unittest.main()
