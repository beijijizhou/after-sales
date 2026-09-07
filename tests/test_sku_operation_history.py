import unittest

import pandas as pd

from ui.inventory.history.workflows.sku_history import (
    build_sku_operation_timeline,
)


SELECTED = {
    "category": "黑白短袖", "brand": "杂牌", "material": "160g",
    "color": "黑", "size": "5XL",
}


class SkuOperationHistoryTests(unittest.TestCase):
    def test_combines_movements_and_activation_changes_by_timestamp(self):
        movements = pd.DataFrame([{
            **SELECTED, "quantity_change": 6840, "quantity_after": 7848,
            "movement_date": "2026-09-06",
            "created_at": "2026-09-06T22:18:00Z",
            "created_by": "胡燕", "reason": "仓库每日出库更正",
            "source_type": "bulk",
        }])
        changes = pd.DataFrame([{
            "changed_at": "2026-09-07T03:00:00Z", "changed_by": "Andy",
            "old_identity": {**SELECTED, "is_active": False},
            "new_identity": {**SELECTED, "is_active": True},
        }])

        result = build_sku_operation_timeline(
            movements, pd.DataFrame(), changes, SELECTED
        )

        self.assertEqual(result.iloc[0]["操作"], "启用 SKU")
        self.assertIn("状态：停用 → 启用", result.iloc[0]["来源/内容"])
        self.assertEqual(result.iloc[1]["库存变动"], "+6,840")
        self.assertEqual(result.iloc[1]["操作前库存"], "1,008")
        self.assertEqual(result.iloc[1]["操作后库存"], "7,848")
        self.assertEqual(result.iloc[2]["操作"], "历史停用")
        self.assertEqual(
            result.iloc[2]["操作人"], "未记录（旧版无审计）"
        )

    def test_does_not_mix_another_size_change(self):
        changes = pd.DataFrame([{
            "changed_at": "2026-09-07T03:00:00Z", "changed_by": "Andy",
            "old_identity": {**SELECTED, "size": "4XL", "is_active": False},
            "new_identity": {**SELECTED, "size": "4XL", "is_active": True},
        }])

        result = build_sku_operation_timeline(
            pd.DataFrame(), pd.DataFrame(), changes, SELECTED
        )

        self.assertTrue(result.empty)


if __name__ == "__main__":
    unittest.main()
