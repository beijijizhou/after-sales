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
    def test_colored_forecast_never_requests_warehouse_audit(self):
        inventory = pd.DataFrame([{
            **inventory_row(), "category": "彩色短袖",
            "brand": "Daisy", "material": "180g", "color": "粉色",
        }])
        usage = pd.DataFrame([{
            **usage_row(), "category": "彩色短袖", "color": "粉色",
        }])

        result = build_incoming_inventory_forecast(
            inventory, pd.DataFrame(), usage, None,
            date(2026, 8, 17), "DTF",
        )

        self.assertTrue(result["录入核对"].eq("不适用").all())
        self.assertTrue(build_inventory_audit_issues(result).empty)

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

        self.assertEqual(usage.iloc[0]["daily_usage"], 123)
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

    def test_inventory_and_usage_remain_visible_without_allocated_container(self):
        inventory = pd.DataFrame([
            {
                "department": "UV", "category": "保温杯",
                "material": "直杯", "brand": "", "color": "",
                "size": "600ML", "quantity": 5000,
            },
            {
                "department": "UV", "category": "保温杯",
                "material": "咖啡杯", "brand": "", "color": "",
                "size": "600ML", "quantity": 3000,
            },
        ])
        usage = pd.DataFrame([
            {
                "department": "UV", "category": "保温杯",
                "planning_material": "直杯", "color": "",
                "size": "600ML", "system_daily_usage": 44,
            },
            {
                "department": "UV", "category": "保温杯",
                "planning_material": "咖啡杯", "color": "",
                "size": "600ML", "system_daily_usage": 20,
            },
        ])

        result = build_incoming_inventory_forecast(
            inventory, pd.DataFrame(), usage, pd.DataFrame(),
            date(2026, 8, 9), "UV",
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(sorted(result["当前库存"].tolist()), [3000, 5000])
        self.assertEqual(sorted(result["系统日均"].tolist()), [20, 44])
        self.assertEqual(result["在途总量"].sum(), 0)
        self.assertNotIn("保温杯｜直杯/咖啡杯箱型待确认", result.to_string())

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

    def test_shortage_before_future_arrival_is_calculated_for_reordering(self):
        result = build_incoming_inventory_forecast(
            pd.DataFrame([inventory_row(quantity=20)]),
            pd.DataFrame([container_row(quantity=100)]),
            pd.DataFrame([usage_row(daily_usage=10)]),
            pd.DataFrame(),
            date(2026, 7, 29),
            "DTF",
        )

        row = result.iloc[0]
        self.assertEqual(row["到货前缺口"], 30)
        self.assertEqual(row["判断"], "到货前可能断货")
        executive = build_incoming_executive_view(result)
        self.assertEqual(
            executive.iloc[0]["货柜衔接"], "无法衔接，缺口 30片"
        )

    def test_overdue_container_uses_tomorrow_for_connection_estimate(self):
        delayed = container_row(quantity=100)
        delayed["expected_arrival_date"] = date(2026, 7, 28)

        result = build_incoming_inventory_forecast(
            pd.DataFrame([inventory_row(quantity=5)]),
            pd.DataFrame([delayed]),
            pd.DataFrame([usage_row(daily_usage=10)]),
            pd.DataFrame(),
            date(2026, 7, 29),
            "DTF",
        )

        row = result.iloc[0]
        self.assertEqual(row["最早到货"], date(2026, 7, 30))
        self.assertEqual(row["距到货天数"], 1)
        self.assertEqual(row["到货前缺口"], 5)
        self.assertIn("延期按明日估算", row["到货概览"])
        self.assertIn("原预计07/28", row["到货安排"])
        executive = build_incoming_executive_view(result)
        self.assertEqual(
            executive.iloc[0]["货柜衔接"],
            "按明日估算，无法衔接，缺口 5片",
        )

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
        self.assertEqual(
            row["到货概览"],
            "08/03 到货 100片｜08/08 到货 200片",
        )
        executive = build_incoming_executive_view(result)
        self.assertNotIn("TEST-1", executive.iloc[0]["到货计划"])
        self.assertNotIn("TEST-2", executive.iloc[0]["到货计划"])
        self.assertEqual(row["到货后预计库存"], 300)
        self.assertEqual(row["到货后可撑天数"], 30)
        self.assertEqual(row["建议点货量"], 450)
        self.assertEqual(row["扣除在途后建议点货量"], 250)

    def test_same_day_containers_are_combined_for_boss_view(self):
        second = container_row(quantity=200)
        second["container_key"] = "TEST-2"
        second["container_no"] = "TEST-2"

        result = build_incoming_inventory_forecast(
            pd.DataFrame([inventory_row()]),
            pd.DataFrame([container_row(), second]),
            pd.DataFrame([usage_row()]),
            pd.DataFrame(),
            date(2026, 7, 29),
            "DTF",
        )

        self.assertEqual(
            result.iloc[0]["到货概览"], "08/03 2柜共到货 300片"
        )

    def test_audit_issues_explain_exact_sku_and_difference(self):
        forecast = pd.DataFrame([{
            "部门": "UV", "品类": "铁板画", "材质口径": "铁牌", "颜色": "白",
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
                "建议点货", "扣除在途后建议点货",
                "到货计划", "在途总量", "到货前缺口", "货柜衔接",
                "到货后可撑",
            ],
        )
        self.assertEqual(result.iloc[0]["SKU"], "铁牌｜白｜2030")
        self.assertEqual(result.iloc[0]["日耗"], 2_302.0)

    def test_pending_shared_cargo_does_not_change_stock_or_daily_usage(self):
        forecast = pd.DataFrame([{
            "部门": "UV", "品类": "保温杯", "材质口径": "直杯", "颜色": "",
            "规格": "600ML", "判断": "当前库存可用",
            "当前库存": 5000, "系统日均": 44.0,
            "当前可撑天数": 113.6, "全部在途货柜": "",
            "到货安排": "", "在途总量": 0,
            "到货前缺口": 0, "到货后可撑天数": 113.6,
            "待确认在途货柜": "第十四柜｜柜号 TRHU5477320",
            "待确认到货安排": (
                "08/17 第十四柜｜柜号 TRHU5477320 351箱"
                "（直杯/咖啡杯箱数分配待确认）"
            ),
            "待确认到货概览": (
                "08/17 到货 351箱（直杯/咖啡杯分配待确认）"
            ),
        }])

        result = build_incoming_executive_view(forecast)

        self.assertEqual(result.iloc[0]["当前库存"], 5000)
        self.assertEqual(result.iloc[0]["日耗"], 44.0)
        self.assertTrue(pd.isna(result.iloc[0]["在途总量"]))
        self.assertIn("直杯/咖啡杯分配待确认", result.iloc[0]["到货计划"])
        self.assertEqual(
            result.iloc[0]["货柜衔接"], "分配待确认，暂不能判断"
        )

    def test_executive_view_groups_business_fields_and_hides_phone_cases(self):
        rows = []
        for category, material, color, size in [
            ("铁板画", "铁牌", "白", "YUAN"),
            ("手机壳", "", "", "IPHONE 15"),
            ("保温杯", "直杯", "", "600ML"),
            ("铁板画", "铝牌", "白", "2030"),
            ("保温杯", "咖啡杯", "", "600ML"),
            ("铁板画", "铁牌", "白", "1040"),
        ]:
            rows.append({
                "部门": "UV", "品类": category, "材质口径": material, "颜色": color,
                "规格": size, "判断": "当前库存可用", "当前库存": 100,
                "系统日均": 10.0, "当前可撑天数": 10.0,
                "全部在途货柜": "", "到货安排": "", "在途总量": 0,
                "到货前缺口": 0, "到货后可撑天数": 10.0,
            })

        result = build_incoming_executive_view(pd.DataFrame(rows))

        self.assertFalse(result["SKU"].str.contains("手机壳").any())
        self.assertEqual(result["SKU"].tolist(), [
            "咖啡杯｜600ML",
            "直杯｜600ML",
            "铝牌｜白｜2030",
            "铁牌｜白｜YUAN",
            "铁牌｜白｜1040",
        ])

    def test_executive_view_sorts_coverage_days_ascending_with_unknown_last(self):
        rows = []
        for size, coverage in [("2030", 20.0), ("1040", None), ("1530", 5.0)]:
            rows.append({
                "部门": "UV", "品类": "铁板画", "材质口径": "铁牌", "颜色": "白",
                "规格": size, "判断": "当前库存可用", "当前库存": 100,
                "系统日均": 10.0, "当前可撑天数": coverage,
                "全部在途货柜": "", "到货安排": "", "在途总量": 0,
                "到货前缺口": 0, "到货后可撑天数": coverage,
            })

        result = build_incoming_executive_view(pd.DataFrame(rows))

        self.assertEqual(result["SKU"].tolist(), [
            "铁牌｜白｜1530",
            "铁牌｜白｜2030",
            "铁牌｜白｜1040",
        ])


if __name__ == "__main__":
    unittest.main()
