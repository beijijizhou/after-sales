import unittest

import pandas as pd

from ui.consumables.operations.entry import _normalize_entry_rows
from ui.consumables.stock import build_latest_costs, filter_items
from utils.auth.constants import ROLE_PERMISSIONS


class ConsumableInventoryTests(unittest.TestCase):
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
        self.assertEqual(preview.iloc[0]["实际数量"], 24)

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


if __name__ == "__main__":
    unittest.main()
