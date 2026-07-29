import unittest

import pandas as pd

from db.finance.summary import (
    build_container_summary,
    build_daily_summary,
    build_department_summary,
    build_finance_overview,
)
from db.finance.repository import _normalize_cost_rows
from ui.finance.cost_editor import find_cost_changes
from utils.auth.constants import NAV_SECTIONS, ROLE_PERMISSIONS


class FinanceSummaryTests(unittest.TestCase):
    def setUp(self):
        self.finance = pd.DataFrame([
            {
                "date": "2026-07-01", "direction": "入库",
                "department": "DTF", "category": "黑白短袖",
                "quantity": 100, "amount": 130, "missing_cost": False,
            },
            {
                "date": "2026-07-02", "direction": "出库",
                "department": "DTF", "category": "黑白短袖",
                "quantity": 40, "amount": 52, "missing_cost": False,
            },
            {
                "date": "2026-07-02", "direction": "出库",
                "department": "UV", "category": "牌类",
                "quantity": 5, "amount": 0, "missing_cost": True,
            },
        ])

    def test_overview_separates_inbound_and_outbound(self):
        result = build_finance_overview(self.finance)
        self.assertEqual(result["inbound_quantity"], 100)
        self.assertEqual(result["outbound_quantity"], 45)
        self.assertEqual(result["outbound_amount"], 52)
        self.assertEqual(result["missing_outbound_quantity"], 5)

    def test_department_summary_calculates_net_change(self):
        result = build_department_summary(self.finance)
        dtf = result[result["部门"] == "DTF"].iloc[0]
        self.assertEqual(dtf["库存数量净变动"], 60)
        self.assertEqual(dtf["成本净增加"], 78)

    def test_daily_summary_keeps_both_directions(self):
        result = build_daily_summary(self.finance)
        second_day = result.iloc[1]
        self.assertEqual(second_day["出库数量"], 45)
        self.assertEqual(second_day["入库数量"], 0)

    def test_container_summary_groups_size_rows(self):
        source = pd.DataFrame([
            {
                "container_key": "A", "container_no": "A",
                "expected_arrival_date": "2026-07-29",
                "actual_arrival_date": None, "status": "未到货",
                "department": "DTF", "category": "黑白短袖",
                "quantity": 60, "amount": 78, "missing_cost": False,
            },
            {
                "container_key": "A", "container_no": "A",
                "expected_arrival_date": "2026-07-29",
                "actual_arrival_date": None, "status": "未到货",
                "department": "DTF", "category": "黑白短袖",
                "quantity": 40, "amount": 52, "missing_cost": False,
            },
        ])
        result = build_container_summary(source)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["数量"], 100)
        self.assertEqual(result.iloc[0]["采购金额"], 130)

    def test_inbound_date_comes_from_cost_lot(self):
        rows = [{
            "id": "lot-a",
            "inbound_movement_id": "movement-a",
            "received_quantity": 10,
            "unit_cost": 1.3,
            "source_type": "bulk",
            "movement_date": "2026-07-29",
            "inventory_items": {
                "department": "DTF",
                "category": "黑白短袖",
                "brand": "Men's",
                "material": "160g",
                "color": "黑",
                "size": "S",
            },
        }]
        result = _normalize_cost_rows(
            rows,
            "inventory_items",
            "received_quantity",
            "入库",
            date_column="movement_date",
        )
        self.assertEqual(str(result.iloc[0]["date"]), "2026-07-29")
        self.assertEqual(result.iloc[0]["amount"], 13)

    def test_finance_dashboard_is_admin_only(self):
        self.assertIn(
            "can_view_finance_dashboard", ROLE_PERMISSIONS["admin"]
        )
        for role, permissions in ROLE_PERMISSIONS.items():
            if role != "admin":
                self.assertNotIn(
                    "can_view_finance_dashboard", permissions
                )

    def test_cost_editor_only_returns_changed_positive_costs(self):
        original = pd.DataFrame([
            {"批次ID": "a", "单位成本": None},
            {"批次ID": "b", "单位成本": 1.3},
            {"批次ID": "c", "单位成本": 2.0},
        ])
        edited = pd.DataFrame([
            {"批次ID": "a", "单位成本": 2.12},
            {"批次ID": "b", "单位成本": 1.3},
            {"批次ID": "c", "单位成本": 0},
        ])
        self.assertEqual(find_cost_changes(original, edited), [("a", 2.12)])

    def test_inventory_navigation_is_grouped(self):
        inventory_section = next(
            items for title, items in NAV_SECTIONS if title == "库存"
        )
        self.assertEqual(
            [label for _, label, _ in inventory_section],
            ["生产库存", "耗材库存", "货柜安排"],
        )
        independent = [
            label
            for title, items in NAV_SECTIONS
            if title is None
            for _, label, _ in items
        ]
        self.assertIn("财务", independent)
        self.assertIn("手机壳图片处理", independent)


if __name__ == "__main__":
    unittest.main()
