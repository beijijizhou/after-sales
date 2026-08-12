import unittest

import pandas as pd

from ui.consumables.operations.entry import _normalize_entry_rows
from ui.consumables.operations.stock_tables import _normalize_initialization
from ui.consumables.stock import build_latest_costs, filter_items
from ui.consumables.page import CONSUMABLE_TABS
from ui.consumables.sku import _copy_defaults
from utils.auth.constants import ROLE_PERMISSIONS


class ConsumableInventoryTests(unittest.TestCase):
    def test_page_exposes_inbound_and_audit_as_primary_tabs(self):
        self.assertEqual(CONSUMABLE_TABS, [
            "当前库存", "点货预测", "消耗模型", "每日耗材出库",
            "耗材入库", "库存设置", "库存流水", "撤销", "SKU 管理",
        ])

    def test_package_entry_converts_to_base_quantity(self):
        edited = pd.DataFrame([{
            "耗材 SKU": "DTF｜白墨｜瓶",
            "录入方式": "整包装",
            "数量": 2,
            "备注": "",
        }])
        labels = {
            "DTF｜白墨｜瓶": {
                "id": "item-1",
                "base_unit": "瓶",
                "package_unit": "箱",
                "units_per_package": 12,
            }
        }

        rows, preview = _normalize_entry_rows(edited, labels, False)

        self.assertEqual(rows[0]["quantity"], 24)
        self.assertEqual(preview.iloc[0]["本次变动（箱）"], 2)
        self.assertEqual(preview.iloc[0]["换算数量"], 24)

    def test_similar_sku_copy_keeps_consumable_identity_and_packaging(self):
        items = pd.DataFrame([{
            "id": "film-100", "category": "膜", "name": "DTF转印膜",
            "specification": "100米/卷", "brand": "奥德利",
            "base_unit": "卷", "package_unit": "箱",
            "units_per_package": 2, "minimum_quantity": 20,
        }])

        defaults = _copy_defaults(items, "film-100")

        self.assertEqual(defaults["category"], "膜")
        self.assertEqual(defaults["name"], "DTF转印膜")
        self.assertEqual(defaults["specification"], "100米/卷")
        self.assertEqual(defaults["brand"], "奥德利")
        self.assertEqual(defaults["base_unit"], "卷")
        self.assertEqual(defaults["units_per_package"], 2)
        self.assertEqual(defaults["minimum_boxes"], 10)

    def test_issue_preview_shows_current_change_and_resulting_boxes(self):
        edited = pd.DataFrame([{
            "耗材 SKU": "墨水｜白色墨水", "箱数": 2, "备注": "",
        }])
        labels = {
            "墨水｜白色墨水": {
                "id": "item-1", "current_quantity": 100,
                "base_unit": "瓶", "package_unit": "箱",
                "units_per_package": 20,
            }
        }

        _, preview = _normalize_entry_rows(
            edited, labels, False, direction=-1
        )

        self.assertEqual(preview.iloc[0]["当前库存（箱）"], 5)
        self.assertEqual(preview.iloc[0]["本次变动（箱）"], -2)
        self.assertEqual(preview.iloc[0]["操作后库存（箱）"], 3)

    def test_latest_cost_uses_newest_priced_movement(self):
        movements = pd.DataFrame([
            {
                "item_id": "item-1",
                "unit_cost": 1.1234,
                "created_at": "2026-07-20T10:00:00Z",
            },
            {
                "item_id": "item-1",
                "unit_cost": 1.5678,
                "created_at": "2026-07-21T10:00:00Z",
            },
        ])

        self.assertEqual(build_latest_costs(movements)["item-1"], 1.5678)

    def test_initialization_records_difference_from_current_stock(self):
        edited = pd.DataFrame([{
            "耗材 SKU": "墨水｜蓝色",
            "当前库存（箱）": 5,
            "目标库存（箱）": 7,
            "备注": "首次盘点",
        }])
        labels = {
            "墨水｜蓝色": {
                "id": "item-1",
                "current_quantity": 20,
                "package_unit": "箱",
                "units_per_package": 4,
            }
        }

        rows, preview = _normalize_initialization(
            edited, labels, include_cost=False
        )

        self.assertEqual(rows[0]["quantity"], 8)
        self.assertEqual(preview.iloc[0]["库存差额（箱）"], 2)

    def test_initialization_can_reduce_incorrect_opening_stock(self):
        edited = pd.DataFrame([{
            "耗材 SKU": "墨水｜蓝色",
            "当前库存（箱）": 5,
            "目标库存（箱）": 2,
            "备注": "",
        }])
        labels = {
            "墨水｜蓝色": {
                "id": "item-1",
                "current_quantity": 20,
                "package_unit": "箱",
                "units_per_package": 4,
            }
        }

        rows, _ = _normalize_initialization(
            edited, labels, include_cost=False
        )

        self.assertEqual(rows[0]["quantity"], -12)

    def test_filters_keep_matching_active_sku(self):
        items = pd.DataFrame([
            {
                "category": "墨水", "name": "白墨",
                "specification": "1L", "brand": "A", "is_active": True,
            },
            {
                "category": "胶带", "name": "透明胶带",
                "specification": "", "brand": "B", "is_active": False,
            },
        ])

        result = filter_items(items, ["墨水"], [], "1L", "仅启用")

        self.assertEqual(result["name"].tolist(), ["白墨"])

    def test_consumable_permissions_follow_inventory_roles(self):
        self.assertIn("can_view_consumables", ROLE_PERMISSIONS["supervisor"])
        self.assertNotIn(
            "can_edit_consumables", ROLE_PERMISSIONS["supervisor"]
        )
        self.assertIn("can_edit_consumables", ROLE_PERMISSIONS["warehouse"])
        self.assertIn(
            "can_manage_consumable_sku", ROLE_PERMISSIONS["after_sales"]
        )

    def test_producer_can_report_consumables_without_warehouse_access(self):
        permissions = ROLE_PERMISSIONS["producer"]

        self.assertIn("can_report_consumables", permissions)
        self.assertIn("can_view_consumables", permissions)
        self.assertIn("can_view_production_data", permissions)
        self.assertNotIn("can_view_cost", permissions)
        self.assertNotIn("can_edit_consumables", permissions)
        self.assertNotIn("can_edit_inventory", permissions)
        self.assertNotIn("can_manage_sku", permissions)
        self.assertNotIn("can_edit_container", permissions)


if __name__ == "__main__":
    unittest.main()
