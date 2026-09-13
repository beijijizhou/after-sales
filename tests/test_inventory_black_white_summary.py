import unittest
from unittest.mock import patch, MagicMock
from datetime import date

import pandas as pd

from automation.production_reference import reweight_partial_production
from db.inventory import (
    SIZE_COLUMNS,
    build_color_inventory_table,
    build_material_color_inventory_table,
)
from db.inventory.planning.consumption_alerts import (
    build_inventory_consumption_alerts,
)
from db.inventory.planning.consumption_comparison import (
    FORECAST_SOURCE_WEIGHTS,
    build_period_model_comparison,
    build_prioritized_consumption_model,
    scale_forecast_daily_total,
)
from db.inventory.planning.consumption import (
    build_consumption_order_mix_comparison,
    build_consumption_order_mix_table,
)
from db.inventory.planning.demand_anomaly import (
    build_demand_anomaly_table,
)
from db.inventory.planning.warehouse_usage import (
    build_warehouse_daily_totals,
    build_stock_outbound_ratio_series,
)
from ui.inventory.planning.anomaly import ANOMALY_COLUMNS
from ui.inventory.planning.forecast_table import FORECAST_COLUMNS
from ui.inventory.planning.forecast_controls import _stable_usage_fingerprint


class InventoryBlackWhiteSummaryTests(unittest.TestCase):
    def test_ratio_charts_render_two_series_and_forward_existing_scope(self):
        from ui.inventory.stock import summary as summary_ui
        stock = pd.DataFrame([
            {"颜色": "黑", "S": 800}, {"颜色": "白", "S": 200},
        ])
        usage = pd.DataFrame([
            {"日期": date(2026, 9, 10), "颜色": "黑", "尺码": "S", "实际出库": 25},
            {"日期": date(2026, 9, 10), "颜色": "白", "尺码": "S", "实际出库": 75},
        ])
        with patch.object(summary_ui, "st") as ui, patch.object(
            summary_ui, "load_daily_outbound_history", return_value=usage,
        ) as load:
            ui.columns.return_value = [MagicMock(), MagicMock()]
            summary_ui.render_black_white_ratio_comparison(
                object(), stock, date(2026, 9, 12), ["S"],
                brands=["Haloo"], materials=["CVC"],
            )
            self.assertEqual(load.call_args.kwargs["brands"], ["Haloo"])
            self.assertEqual(load.call_args.kwargs["materials"], ["CVC"])
            self.assertEqual(ui.altair_chart.call_count, 1)
            for call in ui.altair_chart.call_args_list:
                spec = call.args[0].to_dict()
                self.assertEqual(spec["layer"][0]["encoding"]["y"]["axis"]["format"], ".0%")
                self.assertEqual(spec["layer"][0]["encoding"]["x"]["sort"], [
                    f"{color}{size}" for color in ("黑", "白") for size in SIZE_COLUMNS
                ])

    def test_color_size_ratios_use_whole_stock_and_whole_period_denominators(self):
        stock = pd.DataFrame([
            {"颜色": "黑", "S": 600, "M": 200}, {"颜色": "白", "S": 200},
        ])
        usage = pd.DataFrame([
            {"日期": date(2026, 9, 10), "颜色": "黑", "尺码": "S", "实际出库": 25},
            {"日期": date(2026, 9, 10), "颜色": "白", "尺码": "S", "实际出库": 75},
            {"日期": date(2026, 9, 11), "颜色": "黑", "尺码": "M", "实际出库": 100},
            {"日期": date(2026, 9, 12), "颜色": "黑", "尺码": "S", "实际出库": 999},
        ])
        result = build_stock_outbound_ratio_series(stock, usage, date(2026, 9, 12))
        self.assertEqual(len(result), 32)
        self.assertEqual(result["开始日期"].iloc[0], date(2026, 8, 13))
        self.assertEqual(result["结束日期"].iloc[0], date(2026, 9, 11))
        stock = result[result["曲线"].eq("当前库存比例")].set_index("颜色尺码")
        usage = result[result["曲线"].eq("最近30天出库比例")].set_index("颜色尺码")
        self.assertEqual(stock.loc["黑S", "占比"], .6)
        self.assertEqual(stock.loc["白S", "占比"], .2)
        self.assertEqual(usage.loc["黑S", "占比"], .125)
        self.assertEqual(usage.loc["白S", "占比"], .375)
        self.assertEqual(usage.loc["黑M", "占比"], .5)
        self.assertEqual(usage.loc["白M", "占比"], 0)
        self.assertAlmostEqual(stock["占比"].sum(), 1)
        self.assertAlmostEqual(usage["占比"].sum(), 1)

    def test_ratio_series_does_not_invent_ratios_for_zero_totals(self):
        result = build_stock_outbound_ratio_series(
            pd.DataFrame(), pd.DataFrame(), date(2026, 9, 12),
        )
        self.assertTrue(result["占比"].isna().all())

    def test_warehouse_daily_totals_use_complete_days_and_recorded_dates(self):
        outbound = pd.DataFrame([
            {"日期": date(2026, 8, 9), "实际出库": 100},
            {"日期": date(2026, 8, 9), "实际出库": 50},
            {"日期": date(2026, 9, 7), "实际出库": 300},
            {"日期": date(2026, 9, 8), "实际出库": 999},
        ])

        result = build_warehouse_daily_totals(
            outbound, date(2026, 9, 8), days=30,
        )

        self.assertEqual(result["日期"].tolist(), [
            date(2026, 9, 7), date(2026, 8, 9),
        ])
        self.assertEqual(result["仓库出库量"].tolist(), [300, 150])

    def test_missing_platform_share_uses_historical_weights(self):
        production = pd.DataFrame([{
            "system_daily_usage": 280,
        }])

        result, coverage, method = reweight_partial_production(
            production,
            {"SDS1", "SDS2"},
            {"Haloo", "S2B", "SDS1", "SDS2"},
            {"Haloo": 44, "S2B": 28, "SDS1": 8, "SDS2": 20},
        )

        self.assertAlmostEqual(coverage, 0.28)
        self.assertAlmostEqual(
            float(result.iloc[0]["system_daily_usage"]), 1000
        )
        self.assertIn("最近完整生产数据", method)

    def test_missing_platform_share_falls_back_to_equal_weights(self):
        production = pd.DataFrame([{"system_daily_usage": 300}])

        result, coverage, method = reweight_partial_production(
            production, {"A", "B"}, {"A", "B", "C"}
        )

        self.assertAlmostEqual(coverage, 2 / 3)
        self.assertEqual(int(result.iloc[0]["system_daily_usage"]), 450)
        self.assertIn("等权", method)

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

    def test_material_view_keeps_material_layers_and_combines_brands(self):
        rows = []
        for brand, material, color, small in [
            ("Haloo", "180g", "黑", 10),
            ("SK", "180g", "黑", 5),
            ("Cotton", "CVC", "白", 8),
            ("T64", "160g", "白", 9),
        ]:
            row = {"品牌": brand, "材质": material, "颜色": color, "S": small}
            row.update({size: 0 for size in SIZE_COLUMNS if size != "S"})
            rows.append(row)

        summary = build_material_color_inventory_table(pd.DataFrame(rows))

        self.assertEqual(summary["材质"].tolist(), ["180g", "160g", "CVC"])
        material_180 = summary.loc[summary["材质"] == "180g"].iloc[0]
        self.assertEqual(int(material_180["S"]), 15)

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

    def test_forecast_uses_only_warehouse_outbound_by_default(self):
        comparison = pd.DataFrame([{
            "颜色": "白",
            "尺码": "2XL",
            "15,000模型日耗": 600,
            "平台生产日均": 500,
            "仓库出库日均": 1800,
        }])

        result = build_prioritized_consumption_model(comparison)

        self.assertEqual(FORECAST_SOURCE_WEIGHTS, {"仓库出库日均": 1.0})
        self.assertEqual(int(result.iloc[0]["consumption_quantity"]), 1800)

    def test_missing_platform_reweights_available_sources(self):
        comparison = pd.DataFrame([{
            "颜色": "白",
            "尺码": "2XL",
            "15,000模型日耗": 600,
            "平台生产日均": pd.NA,
            "仓库出库日均": 1300,
        }])

        result = build_prioritized_consumption_model(comparison)

        self.assertEqual(int(result.iloc[0]["consumption_quantity"]), 1300)

    def test_order_mix_table_shows_color_ratio_and_fixed_size_order(self):
        model = pd.DataFrame([
            {"color": "白", "size": "M", "consumption_quantity": 300},
            {"color": "黑", "size": "S", "consumption_quantity": 600},
            {"color": "白", "size": "S", "consumption_quantity": 100},
        ])

        result = build_consumption_order_mix_table(model)

        self.assertEqual(result.columns.tolist(), [
            "颜色", *SIZE_COLUMNS, "合计", "黑白占比",
        ])
        self.assertEqual(result["颜色"].tolist(), ["黑", "白"])
        self.assertEqual(result["合计"].tolist(), [600, 400])
        self.assertEqual(result["黑白占比"].tolist(), [60.0, 40.0])

    def test_order_mix_comparison_shows_baseline_adjustment_and_ratio(self):
        base = pd.DataFrame([
            {"color": "黑", "size": "S", "consumption_quantity": 600},
            {"color": "白", "size": "M", "consumption_quantity": 400},
        ])
        adjusted = pd.DataFrame([
            {"color": "黑", "size": "S", "consumption_quantity": 900},
            {"color": "白", "size": "M", "consumption_quantity": 600},
        ])

        result = build_consumption_order_mix_comparison(base, adjusted)

        self.assertEqual(result.columns.tolist(), [
            "颜色", *SIZE_COLUMNS, "合计", "黑白占比",
        ])
        black = result.loc[result["颜色"] == "黑"].iloc[0]
        white = result.loc[result["颜色"] == "白"].iloc[0]
        self.assertEqual(black["S"], "600→900")
        self.assertEqual(white["M"], "400→600")
        self.assertEqual(black["黑白占比"], "60.0%")

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

    def test_user_daily_override_preserves_sku_mix(self):
        model = pd.DataFrame([
            {"color": "红", "size": "S", "consumption_quantity": 30},
            {"color": "红", "size": "M", "consumption_quantity": 70},
        ])

        adjusted = scale_forecast_daily_total(model, 200)

        self.assertEqual(adjusted["consumption_quantity"].tolist(), [60, 140])

    def test_daily_override_recalculates_forecast_totals(self):
        stock = pd.DataFrame([{
            "颜色": "红", "S": 100, "M": 100,
            **{
                size: 0 for size in SIZE_COLUMNS
                if size not in {"S", "M"}
            },
        }])
        model = pd.DataFrame([
            {"color": "红", "size": "S", "consumption_quantity": 30},
            {"color": "红", "size": "M", "consumption_quantity": 70},
        ])

        adjusted = scale_forecast_daily_total(model, 200)
        forecast = build_inventory_consumption_alerts(
            stock, adjusted, target_days=10,
            inventory_date=date(2026, 9, 8),
            current_date=date(2026, 9, 8),
        )

        self.assertEqual(int(forecast.iloc[0]["预测日耗合计"]), 200)
        self.assertEqual(int(forecast.iloc[0]["建议点货量"]), 1800)

    def test_usage_fingerprint_does_not_depend_on_row_order(self):
        model = pd.DataFrame([
            {"color": "白", "size": "M", "consumption_quantity": 20},
            {"color": "黑", "size": "S", "consumption_quantity": 10},
        ])

        self.assertEqual(
            _stable_usage_fingerprint(model),
            _stable_usage_fingerprint(model.iloc[::-1].reset_index(drop=True)),
        )

    def test_forecast_calculates_target_days_reorder_quantity(self):
        stock = pd.DataFrame([{
            "颜色": "红", "S": 100,
            **{size: 0 for size in SIZE_COLUMNS if size != "S"},
        }])
        model = pd.DataFrame([{
            "color": "红", "size": "S", "consumption_quantity": 10,
        }])

        forecast = build_inventory_consumption_alerts(
            stock, model, target_days=55,
            inventory_date=date(2026, 8, 17),
            current_date=date(2026, 8, 17),
        )

        self.assertEqual(int(forecast.iloc[0]["建议点货量"]), 450)
        self.assertEqual(forecast.iloc[0]["建议点货尺码"], "S:450件")

    def test_forecast_keeps_demand_color_without_inventory_sku_visible(self):
        stock = pd.DataFrame([{
            "颜色": "蓝色", "S": 100,
            **{size: 0 for size in SIZE_COLUMNS if size != "S"},
            "总库存": 100,
        }])
        model = pd.DataFrame([
            {"color": "蓝色", "size": "S", "consumption_quantity": 10},
            {
                "color": "Aurora Blue", "size": "4XL",
                "consumption_quantity": 1,
            },
        ])

        forecast = build_inventory_consumption_alerts(
            stock, model, target_days=55,
            inventory_date=date(2026, 8, 24),
            current_date=date(2026, 8, 24),
        )

        aurora = forecast[forecast["颜色"].eq("Aurora Blue")].iloc[0]
        self.assertEqual(int(aurora["库存基准总数"]), 0)
        self.assertEqual(int(aurora["预测日耗合计"]), 1)
        self.assertEqual(int(aurora["建议点货量"]), 55)

    def test_warehouse_average_uses_outbound_intervals(self):
        model = pd.DataFrame([{
            "color": "白",
            "size": "S",
            "consumption_quantity": 100,
        }])
        outbound = pd.DataFrame([
            {"日期": date(2026, 7, 20), "颜色": "白", "尺码": "S", "实际出库": 100},
            {"日期": date(2026, 7, 25), "颜色": "白", "尺码": "S", "实际出库": 140},
            {"日期": date(2026, 7, 26), "颜色": "白", "尺码": "S", "实际出库": 140},
        ])

        result = build_period_model_comparison(
            model,
            outbound,
            pd.DataFrame(),
            date(2026, 7, 27),
            days=14,
        )

        self.assertAlmostEqual(
            float(result.iloc[0]["仓库出库日均"]),
            280 / 6,
        )
        self.assertEqual(int(result.iloc[0]["仓库有效区间数"]), 2)
        self.assertEqual(int(result.iloc[0]["仓库统计区间数"]), 2)

    def test_anomaly_uses_days_between_outbound_batches(self):
        model = pd.DataFrame([{
            "color": "白",
            "size": "S",
            "consumption_quantity": 100,
        }])
        outbound = pd.DataFrame([
            {"日期": date(2026, 7, 20), "颜色": "白", "尺码": "S", "实际出库": 100},
            {"日期": date(2026, 7, 24), "颜色": "白", "尺码": "S", "实际出库": 300},
            {"日期": date(2026, 7, 26), "颜色": "白", "尺码": "S", "实际出库": 300},
        ])
        inventory = pd.DataFrame([{
            "颜色": "白",
            **{size: 1000 for size in SIZE_COLUMNS},
        }])

        result = build_demand_anomaly_table(
            model,
            outbound,
            inventory,
            current_date=date(2026, 7, 27),
        )

        row = result.iloc[0]
        self.assertEqual(row["上次出库日期"], date(2026, 7, 24))
        self.assertEqual(row["本次出库日期"], date(2026, 7, 26))
        self.assertEqual(int(row["出库间隔天数"]), 2)
        self.assertEqual(int(row["区间日均"]), 150)
        self.assertEqual(int(row["上一区间日均"]), 75)

    def test_risk_columns_appear_before_calculation_columns(self):
        self.assertLess(
            ANOMALY_COLUMNS.index("状态"),
            ANOMALY_COLUMNS.index("上次出库日期"),
        )
        self.assertLess(
            FORECAST_COLUMNS.index("最低剩余天数"),
            FORECAST_COLUMNS.index("库存基准日期"),
        )


if __name__ == "__main__":
    unittest.main()
