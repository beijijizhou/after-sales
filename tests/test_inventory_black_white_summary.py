import unittest

import pandas as pd

from db.inventory import SIZE_COLUMNS, build_color_inventory_table
from db.inventory.planning.consumption_alerts import (
    build_inventory_consumption_alerts,
)
from db.inventory.planning.consumption_comparison import (
    build_prioritized_consumption_model,
)


class InventoryBlackWhiteSummaryTests(unittest.TestCase):
    def test_selected_materials_and_brands_are_combined_by_color(self):
        rows = []
        for brand, material, color, small, medium in [
            ("Haloo", "180g", "黑", 10, 20),
            ("SK", "180g", "黑", 5, 7),
            ("Haloo", "CVC", "黑", 30, 40),
            ("T64", "160g", "白", 8, 9),
        ]:
            row = {
                "品类": "黑白短袖",
                "品牌": brand,
                "材质": material,
                "颜色": color,
                "S": small,
                "M": medium,
            }
            row.update({size: 0 for size in SIZE_COLUMNS if size not in row})
            rows.append(row)

        summary = build_color_inventory_table(pd.DataFrame(rows))

        self.assertEqual(summary["颜色"].tolist(), ["黑", "白"])
        black = summary.loc[summary["颜色"] == "黑"].iloc[0]
        white = summary.loc[summary["颜色"] == "白"].iloc[0]
        self.assertEqual(int(black["S"]), 45)
        self.assertEqual(int(black["M"]), 67)
        self.assertEqual(int(white["S"]), 8)
        self.assertEqual(int(white["M"]), 9)

    def test_forecast_exposes_combined_stock_and_estimated_current_stock(self):
        stock = pd.DataFrame([{
            "颜色": "黑",
            "S": 100,
            "M": 60,
            **{size: 0 for size in SIZE_COLUMNS if size not in {"S", "M"}},
            "总库存": 160,
        }])
        model = pd.DataFrame([
            {"color": "黑", "size": "S", "consumption_quantity": 10},
            {"color": "黑", "size": "M", "consumption_quantity": 5},
        ])
        forecast = build_inventory_consumption_alerts(
            stock,
            model,
            inventory_date=pd.Timestamp("2026-07-25").date(),
            current_date=pd.Timestamp("2026-07-27").date(),
        )

        row = forecast.iloc[0]
        self.assertEqual(int(row["库存基准总数"]), 160)
        self.assertEqual(int(row["预计当前库存"]), 130)
        self.assertEqual(int(row["预测日耗合计"]), 15)

    def test_forecast_prioritizes_model_then_platform_then_warehouse(self):
        comparison = pd.DataFrame([{
            "颜色": "白",
            "尺码": "2XL",
            "15,000模型日耗": 600,
            "平台生产日均": 500,
            "仓库出库日均": 1800,
        }])

        result = build_prioritized_consumption_model(comparison)

        self.assertEqual(int(result.iloc[0]["consumption_quantity"]), 690)

    def test_missing_platform_reweights_available_sources(self):
        comparison = pd.DataFrame([{
            "颜色": "白",
            "尺码": "2XL",
            "15,000模型日耗": 600,
            "平台生产日均": pd.NA,
            "仓库出库日均": 1300,
        }])

        result = build_prioritized_consumption_model(comparison)

        self.assertEqual(int(result.iloc[0]["consumption_quantity"]), 700)

    def test_user_can_change_forecast_weights(self):
        comparison = pd.DataFrame([{
            "颜色": "白",
            "尺码": "2XL",
            "15,000模型日耗": 600,
            "平台生产日均": 500,
            "仓库出库日均": 1800,
        }])

        result = build_prioritized_consumption_model(
            comparison,
            {
                "15,000模型日耗": 80,
                "平台生产日均": 15,
                "仓库出库日均": 5,
            },
        )

        self.assertEqual(int(result.iloc[0]["consumption_quantity"]), 645)


if __name__ == "__main__":
    unittest.main()
