from datetime import date
import unittest

import pandas as pd

from db.inventory.planning.outbound_consumption import (
    apparel_forecast_model,
    build_outbound_consumption_model,
    build_outbound_forecast_usage,
)


class OutboundConsumptionTests(unittest.TestCase):
    def test_one_manual_outbound_date_already_forms_a_model(self):
        history = pd.DataFrame([{
            "日期": date(2026, 9, 22), "品牌": "Haloo", "材质": "180g",
            "颜色": "红", "尺码": "M", "实际出库": 240,
        }])

        result = build_outbound_consumption_model(
            history, date(2026, 9, 23), 30
        )

        self.assertEqual(result.iloc[0]["每日消耗"], 240)
        self.assertEqual(result.iloc[0]["有效数据天数"], 1)
        self.assertEqual(result.iloc[0]["窗口总消耗"], 240)

    def test_later_recorded_category_dates_count_after_sku_first_usage(self):
        history = pd.DataFrame([
            {
                "日期": date(2026, 9, 20), "品牌": "Haloo", "材质": "180g",
                "颜色": "红", "尺码": "M", "实际出库": 300,
            },
            {
                "日期": date(2026, 9, 22), "品牌": "Haloo", "材质": "180g",
                "颜色": "蓝", "尺码": "L", "实际出库": 100,
            },
        ])

        result = build_outbound_consumption_model(
            history, date(2026, 9, 23), 30
        )
        red = result[result["颜色"] == "红"].iloc[0]

        self.assertEqual(red["有效数据天数"], 2)
        self.assertEqual(red["每日消耗"], 150)

    def test_colored_apparel_and_planning_share_one_outbound_result(self):
        model = pd.DataFrame([
            {
                "品牌": "Haloo", "材质": "180g", "颜色": "红", "尺码": "M",
                "每日消耗": 100, "有效数据天数": 2,
                "窗口总消耗": 200, "窗口天数": 30,
            },
            {
                "品牌": "SK", "材质": "180g", "颜色": "红", "尺码": "M",
                "每日消耗": 50, "有效数据天数": 2,
                "窗口总消耗": 100, "窗口天数": 30,
            },
        ])

        usage = build_outbound_forecast_usage(
            model, "DTF", "彩色短袖"
        )
        forecast = apparel_forecast_model(usage)

        self.assertEqual(len(usage), 1)
        self.assertEqual(usage.iloc[0]["daily_usage"], 150)
        self.assertEqual(
            usage.iloc[0]["usage_source_type"], "warehouse_outbound"
        )
        self.assertEqual(forecast.iloc[0]["consumption_quantity"], 150)


if __name__ == "__main__":
    unittest.main()
