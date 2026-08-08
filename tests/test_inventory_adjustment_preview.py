import unittest

import pandas as pd

from db.inventory import SIZE_COLUMNS
from ui.inventory.operations.adjustment_preview import (
    build_adjustment_stock_comparison,
)


class InventoryAdjustmentPreviewTests(unittest.TestCase):
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
            result["数据口径"].tolist(),
            ["当前库存", "本次入库 (+)", "操作后库存"],
        )
        self.assertEqual(result.iloc[0]["S"], 100)
        self.assertEqual(result.iloc[1]["S"], 10)
        self.assertEqual(result.iloc[2]["S"], 110)
        self.assertEqual(result.iloc[2]["M"], 220)

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

        self.assertEqual(result.iloc[1]["L"], -60)
        self.assertEqual(result.iloc[2]["L"], -10)


if __name__ == "__main__":
    unittest.main()
