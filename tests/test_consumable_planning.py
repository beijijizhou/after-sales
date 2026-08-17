from datetime import date
import unittest

import pandas as pd

from db.consumables.planning import (
    build_consumable_consumption_model,
    build_consumable_reorder_forecast,
)


class ConsumablePlanningTests(unittest.TestCase):
    def test_consumption_model_uses_active_issue_batches_only(self):
        items = pd.DataFrame([{
            "id": "item-1",
            "category": "墨水",
            "name": "白墨",
            "specification": "1L",
            "brand": "",
            "base_unit": "瓶",
            "package_unit": "箱",
            "units_per_package": 20,
            "current_quantity": 100,
            "minimum_quantity": 40,
            "is_active": True,
        }])
        batches = pd.DataFrame([
            {
                "id": "batch-1",
                "movement_type": "issue",
                "movement_date": "2026-08-10",
                "reversal_of_batch_id": None,
            },
            {
                "id": "batch-2",
                "movement_type": "issue",
                "movement_date": "2026-08-11",
                "reversal_of_batch_id": "batch-1",
            },
            {
                "id": "batch-3",
                "movement_type": "inbound",
                "movement_date": "2026-08-11",
                "reversal_of_batch_id": None,
            },
        ])
        movements = pd.DataFrame([
            {
                "id": "move-1",
                "batch_id": "batch-1",
                "item_id": "item-1",
                "movement_date": "2026-08-10",
                "quantity_change": -40,
                "reversal_of_movement_id": None,
            },
            {
                "id": "move-2",
                "batch_id": "batch-2",
                "item_id": "item-1",
                "movement_date": "2026-08-11",
                "quantity_change": 40,
                "reversal_of_movement_id": "move-1",
            },
            {
                "id": "move-3",
                "batch_id": "batch-3",
                "item_id": "item-1",
                "movement_date": "2026-08-11",
                "quantity_change": 20,
                "reversal_of_movement_id": None,
            },
        ])

        result = build_consumable_consumption_model(
            items, batches, movements, lookback_days=14,
            current_date=date(2026, 8, 12),
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["总领用量"], 0.0)
        self.assertEqual(result.iloc[0]["有效数据天数"], 0)
        self.assertEqual(result.iloc[0]["最近领用日均"], 0.0)
        self.assertEqual(result.iloc[0]["自然窗口日均"], 0.0)
        self.assertEqual(result.iloc[0]["窗口天数"], 14)

    def test_consumption_model_summarizes_recent_issue_history(self):
        items = pd.DataFrame([{
            "id": "item-1",
            "category": "膜",
            "name": "转印膜",
            "specification": "100米",
            "brand": "A",
            "base_unit": "卷",
            "package_unit": "箱",
            "units_per_package": 2,
            "current_quantity": 24,
            "minimum_quantity": 8,
            "is_active": True,
        }])
        batches = pd.DataFrame([
            {
                "id": "batch-1",
                "movement_type": "issue",
                "movement_date": "2026-08-10",
                "reversal_of_batch_id": None,
            },
            {
                "id": "batch-2",
                "movement_type": "issue",
                "movement_date": "2026-08-11",
                "reversal_of_batch_id": None,
            },
        ])
        movements = pd.DataFrame([
            {
                "id": "move-1",
                "batch_id": "batch-1",
                "item_id": "item-1",
                "movement_date": "2026-08-10",
                "quantity_change": -6,
                "reversal_of_movement_id": None,
            },
            {
                "id": "move-2",
                "batch_id": "batch-2",
                "item_id": "item-1",
                "movement_date": "2026-08-11",
                "quantity_change": -10,
                "reversal_of_movement_id": None,
            },
        ])

        result = build_consumable_consumption_model(
            items, batches, movements, lookback_days=14,
            current_date=date(2026, 8, 12),
        )

        self.assertEqual(result.iloc[0]["总领用量"], 16.0)
        self.assertEqual(result.iloc[0]["有效数据天数"], 2)
        self.assertEqual(result.iloc[0]["最近领用日均"], 8.0)
        self.assertAlmostEqual(result.iloc[0]["自然窗口日均"], 16 / 14, places=2)
        self.assertEqual(result.iloc[0]["窗口天数"], 14)
        self.assertEqual(result.iloc[0]["当前库存（箱）"], 12.0)
        self.assertEqual(result.iloc[0]["最低库存（箱）"], 4.0)

    def test_reorder_forecast_calculates_coverage_and_recommended_order(self):
        model = pd.DataFrame([{
            "item_id": "item-1",
            "分类": "墨水",
            "耗材名称": "白墨",
            "规格/型号": "1L",
            "品牌": "",
            "基础单位": "瓶",
            "包装单位": "箱",
            "每箱数量": 20,
            "最近领用日均": 10.0,
            "有效数据天数": 5,
            "自然窗口日均": 3.57,
            "总领用量": 50.0,
            "窗口天数": 14,
            "当前库存": 30.0,
            "当前库存（箱）": 1.5,
            "最低库存": 40.0,
            "最低库存（箱）": 2.0,
        }])

        result = build_consumable_reorder_forecast(
            model,
            current_date=date(2026, 8, 12),
            coverage_days=14,
        )

        row = result.iloc[0]
        self.assertEqual(row["库存基准总数"], 30.0)
        self.assertEqual(row["预测日耗合计"], 10.0)
        self.assertEqual(row["最低剩余天数"], 3)
        self.assertEqual(row["安全库存缺口"], 10.0)
        self.assertEqual(row["建议点货量"], 110)
        self.assertEqual(row["建议点货量（箱）"], 5.5)
        self.assertEqual(row["预计最早耗尽日期"], date(2026, 8, 15))
        self.assertEqual(row["有效数据天数"], 5)
        self.assertEqual(row["自然窗口日均"], 3.57)
        self.assertEqual(row["窗口天数"], 14)


if __name__ == "__main__":
    unittest.main()
