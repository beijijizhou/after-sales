import unittest
from pathlib import Path

import pandas as pd

from db.inventory.operations.outbound_verification import (
    find_outbound_warehouse_shortages,
)
from db.inventory.warehouses import (
    build_transfer_line_editor,
    build_warehouse_distribution,
    normalize_transfer_execution_lines,
    plan_outbound_cover_transfers,
)
from ui.inventory.transfers.processing import build_transfer_export
from utils.auth.constants import NAV_ITEMS, PAGE_ACCESS


class InventoryWarehouseTests(unittest.TestCase):
    def setUp(self):
        self.items = pd.DataFrame([
            {
                "id": "sku-l", "department": "DTF",
                "category": "黑白短袖", "material": "180g",
                "brand": "Haloo", "color": "黑", "size": "L",
                "quantity": 100,
            },
            {
                "id": "sku-s", "department": "DTF",
                "category": "黑白短袖", "material": "180g",
                "brand": "Haloo", "color": "黑", "size": "S",
                "quantity": 80,
            },
        ])

    def test_distribution_keeps_company_total_and_warehouse_locations(self):
        balances = pd.DataFrame([
            {
                "inventory_item_id": "sku-l", "warehouse_code": "25",
                "quantity": 30, "location_note": "拣货区",
            },
            {
                "inventory_item_id": "sku-l", "warehouse_code": "60",
                "quantity": 50, "location_note": "A区",
            },
            {
                "inventory_item_id": "sku-s", "warehouse_code": "25",
                "quantity": 80, "location_note": "",
            },
        ])
        orders = pd.DataFrame([{"id": "transfer-1", "status": "in_transit"}])
        lines = pd.DataFrame([{
            "transfer_order_id": "transfer-1", "inventory_item_id": "sku-l",
            "quantity_sent": 20, "quantity_received": 0,
        }])

        result = build_warehouse_distribution(
            self.items, balances, orders, lines
        )

        self.assertEqual(result["尺码"].tolist(), ["S", "L"])
        row = result[result["库存ID"] == "sku-l"].iloc[0]
        self.assertEqual(row["25仓"], 30)
        self.assertEqual(row["60仓"], 50)
        self.assertEqual(row["在途/待核对"], 20)
        self.assertEqual(row["未分配差额"], 0)
        self.assertEqual(row["总库存"], 100)
        self.assertEqual(row["60库位"], "A区")

    def test_transfer_editor_uses_actual_quantity_not_request_quantity(self):
        lines = pd.DataFrame([{
            **self.items.iloc[0].to_dict(),
            "id": "line-1", "transfer_order_id": "transfer-1",
            "inventory_item_id": "sku-l", "quantity_sent": 0,
            "quantity_received": 0, "source_location": "",
            "target_location": "", "note": "补齐断码",
        }])

        editor = build_transfer_line_editor(lines, mode="dispatch")
        editor.loc[0, "实际发出"] = 36
        payload = normalize_transfer_execution_lines(editor)

        self.assertNotIn("申请数量", editor.columns)
        self.assertEqual(payload[0]["line_id"], "line-1")
        self.assertEqual(payload[0]["quantity"], 36)

    def test_warehouse_transfer_is_an_inventory_navigation_page(self):
        rows = [item for item in NAV_ITEMS if item[0] == "inventory_transfer"]

        self.assertEqual(
            rows,
            [("inventory_transfer", "仓库调拨", "pages/14_仓库调拨.py")],
        )
        self.assertEqual(
            PAGE_ACCESS["inventory_transfer"], "can_view_inventory"
        )

    def test_outbound_flags_sku_whose_stock_sits_in_reserve_warehouse(self):
        outbound = pd.DataFrame([
            {"品牌": "Haloo", "材质": "CVC", "颜色": "黑", "尺码": "3XL", "数量": 2000},
            {"品牌": "Haloo", "材质": "CVC", "颜色": "黑", "尺码": "L", "数量": 2000},
        ])
        inventory = pd.DataFrame([
            {"id": "sku-3xl", "brand": "Haloo", "material": "CVC", "style": "",
             "color": "黑", "size": "3XL", "quantity": 21542},
            {"id": "sku-l", "brand": "Haloo", "material": "CVC", "style": "",
             "color": "黑", "size": "L", "quantity": 181966},
        ])
        balances = pd.DataFrame([
            {"inventory_item_id": "sku-3xl", "warehouse_code": "25", "quantity": 1342},
            {"inventory_item_id": "sku-3xl", "warehouse_code": "60", "quantity": 20200},
            {"inventory_item_id": "sku-l", "warehouse_code": "25", "quantity": 157066},
            {"inventory_item_id": "sku-l", "warehouse_code": "60", "quantity": 24900},
        ])

        shortages = find_outbound_warehouse_shortages(
            outbound, inventory, balances, "25"
        )

        self.assertEqual(shortages["尺码"].tolist(), ["3XL"])
        row = shortages.iloc[0]
        self.assertEqual(int(row["当前库存"]), 21542)
        self.assertEqual(int(row["出库仓库存"]), 1342)
        self.assertEqual(int(row["其他仓库存"]), 20200)
        self.assertEqual(int(row["出库仓缺口"]), 658)

    def test_cover_plan_takes_shortage_from_reserve_warehouses_in_order(self):
        shortages = pd.DataFrame([{
            "inventory_item_id": "sku-3xl", "品牌": "Haloo", "材质": "CVC",
            "款式": "", "颜色": "黑", "尺码": "3XL", "出库仓缺口": 658,
        }])
        balances = pd.DataFrame([
            {"inventory_item_id": "sku-3xl", "warehouse_code": "25", "quantity": 1342},
            {"inventory_item_id": "sku-3xl", "warehouse_code": "70", "quantity": 900},
            {"inventory_item_id": "sku-3xl", "warehouse_code": "60", "quantity": 500},
        ])

        plan, uncovered = plan_outbound_cover_transfers(shortages, balances, "25")

        self.assertEqual(uncovered, 0)
        self.assertEqual(plan["来源仓"].tolist(), ["60", "70"])
        self.assertEqual(plan["调拨数量"].tolist(), [500, 158])

        _, missing = plan_outbound_cover_transfers(
            shortages, balances[balances["warehouse_code"] != "70"], "25"
        )
        self.assertEqual(missing, 158)

    def test_outbound_warehouse_check_ignores_company_wide_shortage(self):
        outbound = pd.DataFrame([
            {"品牌": "Haloo", "材质": "CVC", "颜色": "白", "尺码": "S", "数量": 500},
        ])
        inventory = pd.DataFrame([
            {"id": "sku-s", "brand": "Haloo", "material": "CVC", "style": "",
             "color": "白", "size": "S", "quantity": 300},
        ])
        balances = pd.DataFrame([
            {"inventory_item_id": "sku-s", "warehouse_code": "25", "quantity": 300},
        ])

        shortages = find_outbound_warehouse_shortages(
            outbound, inventory, balances, "25"
        )

        self.assertTrue(shortages.empty)

    def test_migration_keeps_transfer_atomic_and_syncs_warehouse_25(self):
        paths = sorted(Path("sql/inventory/warehouses").glob("*.sql"))
        sql = "\n".join(path.read_text(encoding="utf-8") for path in paths)

        self.assertEqual(len(paths), 6)
        self.assertIn("inventory_movement_warehouse_sync", sql)
        for path in (paths[0], paths[5]):
            self.assertIn(
                "coalesce(style, '') = coalesce(new.style, '')",
                path.read_text(encoding="utf-8"),
            )
        self.assertIn("default '25'", sql)
        self.assertIn("create_inventory_transfer_request", sql)
        self.assertIn("dispatch_inventory_transfer", sql)
        self.assertIn("receive_inventory_transfer", sql)
        self.assertIn("complete_pending_inventory_transfer", sql)
        self.assertIn("reverse_inventory_transfer", sql)
        self.assertIn("record_inventory_transfer_baseline", sql)
        self.assertIn("balance_effect_applied", sql)
        for path in paths:
            migration = path.read_text(encoding="utf-8")
            self.assertRegex(migration, r"(?s)^begin;.*commit;")

    def test_transfer_export_contains_order_context(self):
        order = {
            "transfer_number": "TR-20260808-ABC123",
            "status": "in_transit",
            "from_warehouse": "60",
            "to_warehouse": "25",
        }
        detail = pd.DataFrame([{
            "明细ID": "line-1", "库存ID": "sku-l",
            "材质": "180g", "尺码": "L", "已发出": 20,
        }])

        result = build_transfer_export(order, detail)

        self.assertEqual(result.loc[0, "调拨单号"], "TR-20260808-ABC123")
        self.assertEqual(result.loc[0, "状态"], "运输中")
        self.assertNotIn("明细ID", result.columns)
        self.assertNotIn("库存ID", result.columns)


if __name__ == "__main__":
    unittest.main()
