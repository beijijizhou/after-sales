from datetime import date
import unittest

import pandas as pd

from db.inventory.planning.uv_consumption import (
    build_uv_consumption_model,
    build_uv_forecast_usage,
    filter_uv_model_to_active_skus,
)


class UVConsumptionModelTests(unittest.TestCase):
    def test_inactive_sku_is_removed_from_consumption_model(self):
        model = pd.DataFrame([
            {
                "品类": "铁板画", "材质": "铁牌", "颜色": "白",
                "型号": "CHEPAI", "每日消耗": 23.0, "有效数据天数": 10,
            },
            {
                "品类": "铁板画", "材质": "铁牌", "颜色": "白",
                "型号": "2030", "每日消耗": 2485.0, "有效数据天数": 13,
            },
        ])
        active = pd.DataFrame([{
            "category": "铁板画", "material": "铁牌",
            "color": "白", "size": "2030",
        }])

        result = filter_uv_model_to_active_skus(model, active)

        self.assertEqual(result["型号"].tolist(), ["2030"])
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

    def test_adapts_google_sheet_model_for_incoming_forecast(self):
        model = pd.DataFrame([{
            "品类": "铁板画",
            "材质": "铁牌",
            "颜色": "白",
            "型号": "2030",
            "每日消耗": 2302.0,
            "有效数据天数": 2,
        }])

        result = build_uv_forecast_usage(model)

        self.assertEqual(result.iloc[0]["department"], "UV")
        self.assertEqual(result.iloc[0]["category"], "铁板画")
        self.assertEqual(result.iloc[0]["planning_material"], "铁牌")
        self.assertEqual(result.iloc[0]["size"], "2030")
        self.assertEqual(
            result.iloc[0]["daily_usage"], 2302.0
        )
        self.assertEqual(result.iloc[0]["usage_source_type"], "google_sheets")

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

        self.assertEqual(result.iloc[0]["每日消耗"], 939.3)
        self.assertEqual(result.iloc[0]["有效数据天数"], 3)

    def test_material_reclassification_nets_daily_consumption(self):
        rows = pd.DataFrame([
            {
                "category": "铁板画", "material": "铝牌",
                "color": "白", "size": "2030",
                "quantity_change": -2378,
                "movement_date": "2026-07-28",
                "reason": "Google Sheets UV每日消耗｜2026-07-28｜旧扣减",
                "batch_id": "a", "reversal_of_batch_id": None,
            },
            {
                "category": "铁板画", "material": "铝牌",
                "color": "白", "size": "2030",
                "quantity_change": 2144,
                "movement_date": "2026-07-28",
                "reason": "Google Sheets UV每日消耗｜2026-07-28｜材质更正",
                "batch_id": "b", "reversal_of_batch_id": None,
            },
            {
                "category": "铁板画", "material": "铁牌",
                "color": "白", "size": "2030",
                "quantity_change": -2144,
                "movement_date": "2026-07-28",
                "reason": "Google Sheets UV每日消耗｜2026-07-28｜材质更正",
                "batch_id": "b", "reversal_of_batch_id": None,
            },
        ])

        result = build_uv_consumption_model(rows, date(2026, 7, 28))

        aluminum = result[result["材质"] == "铝牌"].iloc[0]
        iron = result[result["材质"] == "铁牌"].iloc[0]
        self.assertEqual(aluminum["每日消耗"], 234.0)
        self.assertEqual(iron["每日消耗"], 2144.0)

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
