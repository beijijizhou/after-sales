from datetime import date
import unittest

import pandas as pd

from db.inventory.planning.incoming import (
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
        self.assertEqual(row["货柜数量"], 100)
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
        self.assertEqual(row["货柜数量"], 50)
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


if __name__ == "__main__":
    unittest.main()
