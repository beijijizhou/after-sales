from datetime import date
import unittest

import pandas as pd

from db.inventory.planning.uv_consumption import (
    build_uv_container_coverage,
    build_uv_consumption_model,
)


class UVConsumptionModelTests(unittest.TestCase):
    def test_builds_effective_daily_average_from_google_sheet_rows(self):
        rows = pd.DataFrame([
            {
                "material": "铁牌",
                "category": "铁板画",
                "color": "白",
                "size": "1040",
                "quantity_change": -100,
                "movement_date": "2026-07-28",
                "reason": "Google Sheets UV每日消耗｜2026-07-28",
                "batch_id": "a",
                "reversal_of_batch_id": None,
            },
            {
                "material": "铁牌",
                "category": "铁板画",
                "color": "白",
                "size": "1040",
                "quantity_change": -200,
                "movement_date": "2026-07-29",
                "reason": "Google Sheets UV每日消耗｜2026-07-29",
                "batch_id": "b",
                "reversal_of_batch_id": None,
            },
            {
                "material": "铁牌",
                "category": "铁板画",
                "color": "白",
                "size": "2030",
                "quantity_change": -900,
                "movement_date": "2026-07-29",
                "reason": "临时库存调整",
                "batch_id": "c",
                "reversal_of_batch_id": None,
            },
        ])

        result = build_uv_consumption_model(
            rows, date(2026, 7, 29)
        )

        self.assertEqual(result.iloc[0]["每日消耗"], 150.0)
        self.assertEqual(result.iloc[0]["有效数据天数"], 2)

    def test_connects_daily_usage_to_inventory_and_nearest_container(self):
        model = pd.DataFrame([{
            "品类": "手机壳", "材质": "", "颜色": "",
            "型号": "IPHONE 15", "每日消耗": 2.0,
            "有效数据天数": 7,
        }])
        inventory = pd.DataFrame([{
            "category": "手机壳", "material": "", "color": "",
            "size": "iPhone 15", "quantity": 20,
        }])
        containers = pd.DataFrame([{
            "category": "手机壳", "material": "", "color": "",
            "size": "Iphone 15", "quantity": 30,
            "container_no": "10柜",
            "expected_arrival_date": "2026-08-05",
        }])

        result = build_uv_container_coverage(
            model, inventory, containers
        )

        self.assertEqual(result.iloc[0]["当前可撑天数"], 10.0)
        self.assertEqual(result.iloc[0]["货柜数量"], 30)
        self.assertEqual(result.iloc[0]["到货后可撑天数"], 25.0)

    def test_2030_models_restart_after_substitution_ends(self):
        rows = pd.DataFrame([
            {
                "category": "铁板画", "material": "铝牌",
                "color": "白", "size": "2030",
                "quantity_change": -2500,
                "movement_date": "2026-07-28",
                "reason": "Google Sheets UV每日消耗｜2026-07-28",
                "batch_id": "a", "reversal_of_batch_id": None,
            },
            {
                "category": "铁板画", "material": "铝牌",
                "color": "白", "size": "2030",
                "quantity_change": -136,
                "movement_date": "2026-07-29",
                "reason": "Google Sheets UV每日消耗｜2026-07-29",
                "batch_id": "b", "reversal_of_batch_id": None,
            },
            {
                "category": "铁板画", "material": "铝牌",
                "color": "白", "size": "2030",
                "quantity_change": -182,
                "movement_date": "2026-07-30",
                "reason": "Google Sheets UV每日消耗｜2026-07-30",
                "batch_id": "c", "reversal_of_batch_id": None,
            },
        ])

        result = build_uv_consumption_model(
            rows, date(2026, 7, 30)
        )

        self.assertEqual(result.iloc[0]["每日消耗"], 159.0)
        self.assertEqual(result.iloc[0]["有效数据天数"], 2)

    def test_zero_days_count_only_after_sku_first_usage(self):
        rows = pd.DataFrame([
            {
                "category": "铁板画", "material": "铁牌",
                "color": "白", "size": "1040",
                "quantity_change": -100,
                "movement_date": "2026-07-28",
                "reason": "Google Sheets UV每日消耗｜2026-07-28",
                "batch_id": "a", "reversal_of_batch_id": None,
            },
            {
                "category": "铁板画", "material": "铁牌",
                "color": "白", "size": "2030",
                "quantity_change": -200,
                "movement_date": "2026-07-29",
                "reason": "Google Sheets UV每日消耗｜2026-07-29",
                "batch_id": "b", "reversal_of_batch_id": None,
            },
        ])

        result = build_uv_consumption_model(
            rows, date(2026, 7, 29)
        )

        self.assertEqual(result["有效数据天数"].tolist(), [2, 1])
        self.assertEqual(result["每日消耗"].tolist(), [50.0, 200.0])


if __name__ == "__main__":
    unittest.main()
