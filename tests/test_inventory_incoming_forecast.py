from datetime import date
import unittest

import pandas as pd

from db.inventory.planning.incoming import (
    build_incoming_executive_view,
    build_inventory_audit_issues,
    build_incoming_inventory_forecast,
    normalize_forecast_usage,
)


def inventory_row(quantity=100):
    return {
        "department": "DTF",
        "category": "黑白短袖",
        "brand": "Haloo",
        "material": "CVC",
        "color": "黑",
        "size": "L",
        "quantity": quantity,
    }


def container_row(status="在途", quantity=100):
    return {
        **inventory_row(quantity),
        "container_key": "TEST-1",
        "container_no": "TEST-1",
        "status": status,
        "expected_arrival_date": date(2026, 8, 3),
        "actual_arrival_date": (
            date(2026, 7, 29) if status == "已到柜" else None
        ),
    }


def usage_row(daily_usage=10):
    return {
        "department": "DTF",
        "category": "黑白短袖",
        "planning_material": "全部品牌/材质",
        "color": "黑",
        "size": "L",
        "system_daily_usage": daily_usage,
    }


class InventoryIncomingForecastTests(unittest.TestCase):
    def test_reuses_reorder_forecast_daily_usage(self):
        usage = normalize_forecast_usage(
            pd.DataFrame([{
                "color": "黑",
                "size": "L",
                "consumption_quantity": 123,
            }]),
            "DTF",
            "黑白短袖",
        )

        self.assertEqual(usage.iloc[0]["system_daily_usage"], 123)
        self.assertEqual(
            usage.iloc[0]["planning_material"], "全部品牌/材质"
        )

    def test_forecast_shows_inventory_before_and_after_arrival(self):
        result = build_incoming_inventory_forecast(
            pd.DataFrame([inventory_row()]),
            pd.DataFrame([container_row()]),
            pd.DataFrame([usage_row()]),
            pd.DataFrame(),
            date(2026, 7, 29),
            "DTF",
        )

        row = result.iloc[0]
        self.assertEqual(row["距到货天数"], 5)
        self.assertEqual(row["到货前预计剩余"], 50)
        self.assertEqual(row["在途总量"], 100)
        self.assertEqual(row["到货后预计库存"], 150)
        self.assertEqual(row["到货后可撑天数"], 15)
        self.assertEqual(row["判断"], "可撑到到货")

    def test_arrived_container_is_pending_instead_of_current_stock(self):
        result = build_incoming_inventory_forecast(
            pd.DataFrame([inventory_row()]),
            pd.DataFrame([container_row(status="已到柜", quantity=50)]),
            pd.DataFrame([usage_row()]),
            pd.DataFrame(),
            date(2026, 7, 29),
            "DTF",
        )

        row = result.iloc[0]
        self.assertEqual(row["当前库存"], 100)
        self.assertEqual(row["在途总量"], 50)
        self.assertEqual(row["到货后预计库存"], 150)
        self.assertEqual(row["距到货天数"], 0)
        self.assertEqual(row["判断"], "已到柜待入库")

    def test_low_coverage_after_arrival_is_highlighted(self):
        result = build_incoming_inventory_forecast(
            pd.DataFrame([inventory_row(quantity=60)]),
            pd.DataFrame([container_row(quantity=20)]),
            pd.DataFrame([usage_row()]),
            pd.DataFrame(),
            date(2026, 7, 29),
            "DTF",
        )

        row = result.iloc[0]
        self.assertEqual(row["到货前预计剩余"], 10)
        self.assertEqual(row["到货后预计库存"], 30)
        self.assertEqual(row["判断"], "到货后库存仍偏低")

    def test_forecast_combines_every_in_transit_container(self):
        second = container_row(quantity=200)
        second["container_key"] = "TEST-2"
        second["container_no"] = "TEST-2"
        second["expected_arrival_date"] = date(2026, 8, 8)

        result = build_incoming_inventory_forecast(
            pd.DataFrame([inventory_row()]),
            pd.DataFrame([container_row(), second]),
            pd.DataFrame([usage_row()]),
            pd.DataFrame(),
            date(2026, 7, 29),
            "DTF",
        )

        row = result.iloc[0]
        self.assertEqual(row["全部在途货柜"], "TEST-1 / TEST-2")
        self.assertEqual(row["在途总量"], 300)
        self.assertEqual(row["最早到货"], date(2026, 8, 3))
        self.assertEqual(row["最晚到货"], date(2026, 8, 8))
        self.assertIn("08/03 TEST-1 100", row["到货安排"])
        self.assertIn("08/08 TEST-2 200", row["到货安排"])
        self.assertEqual(row["到货后预计库存"], 300)
        self.assertEqual(row["到货后可撑天数"], 30)

    def test_audit_issues_explain_exact_sku_and_difference(self):
        forecast = pd.DataFrame([{
            "品类": "铁板画", "材质口径": "铁牌", "颜色": "白",
            "规格": "2030", "系统日均": 2302.0,
            "仓库申报日均": 1200.0, "录入核对": "需核对",
        }])

        issues = build_inventory_audit_issues(forecast)

        self.assertEqual(issues.iloc[0]["规格"], "2030")
        self.assertEqual(issues.iloc[0]["日均差额"], -1102.0)
        self.assertAlmostEqual(
            issues.iloc[0]["差异比例"], 1102 / 2302 * 100
        )
        self.assertIn("低于", issues.iloc[0]["核对建议"])

    def test_uv_does_not_create_warehouse_declaration_issues(self):
        inventory = pd.DataFrame([{
            "department": "UV", "category": "铁板画",
            "brand": "", "material": "铁牌", "color": "白",
            "size": "2030", "quantity": 35_396,
        }])
        container = pd.DataFrame([{
            **inventory.iloc[0].to_dict(),
            "container_key": "第十三柜", "container_no": "第十三柜",
            "status": "在途",
            "expected_arrival_date": date(2026, 8, 17),
            "actual_arrival_date": None, "quantity": 45_000,
        }])
        usage = pd.DataFrame([{
            "department": "UV", "category": "铁板画",
            "planning_material": "铁牌", "color": "白",
            "size": "2030", "system_daily_usage": 2_302,
        }])

        forecast = build_incoming_inventory_forecast(
            inventory, container, usage, pd.DataFrame(),
            date(2026, 7, 30), "UV",
        )

        self.assertEqual(forecast.iloc[0]["录入核对"], "不适用")
        self.assertTrue(build_inventory_audit_issues(forecast).empty)

    def test_executive_view_combines_sku_and_keeps_decision_columns(self):
        forecast = pd.DataFrame([{
            "品类": "铁板画", "材质口径": "铁牌", "颜色": "白",
            "规格": "2030", "判断": "到货前可能断货",
            "当前库存": 35_396, "系统日均": 2_302.0,
            "当前可撑天数": 15.4, "全部在途货柜": "第十三柜",
            "到货安排": "08/17 第十三柜 45,000",
            "在途总量": 45_000, "到货前缺口": 6_040,
            "到货后可撑天数": 19.5,
        }])

        result = build_incoming_executive_view(forecast)

        self.assertEqual(
            result.columns.tolist(),
            [
                "SKU", "判断", "当前库存", "日耗", "可撑天数",
                "全部在途货柜", "到货安排", "在途总量", "到货前缺口",
                "到货后可撑",
            ],
        )
        self.assertEqual(result.iloc[0]["SKU"], "铁板画｜铁牌｜白｜2030")
        self.assertEqual(result.iloc[0]["日耗"], 2_302.0)


if __name__ == "__main__":
    unittest.main()
