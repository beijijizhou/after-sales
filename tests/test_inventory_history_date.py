import unittest

import pandas as pd

from ui.inventory.history.history import filter_inventory_history_data


class InventoryHistoryDateTests(unittest.TestCase):
    def test_history_filter_keeps_all_dates_for_selected_sku(self):
        movements = pd.DataFrame([
            {
                "category": "手机壳", "brand": "", "material": "TPU",
                "color": "", "size": "IPHONE 15",
                "movement_date": "2026-07-28", "quantity_change": 10,
                "department": "UV", "reason": "初始化",
                "created_at": "2026-07-28T12:00:00Z",
            },
            {
                "category": "手机壳", "brand": "", "material": "TPU",
                "color": "", "size": "IPHONE 15",
                "movement_date": "2026-07-30", "quantity_change": -2,
                "department": "UV", "reason": "生产扣减",
                "created_at": "2026-07-30T12:00:00Z",
            },
        ])
        history_data = (movements, pd.DataFrame(), pd.DataFrame())

        all_dates, _, _ = filter_inventory_history_data(
            history_data, "手机壳", [], ["TPU"], [], ["IPHONE 15"],
        )

        self.assertEqual(len(all_dates), 2)

    def test_history_filter_limits_rows_by_color_and_size(self):
        common = {
            "department": "DTF", "quantity_change": -10,
            "movement_date": "2026-08-08", "reason": "仓库每日出货",
            "created_at": "2026-08-08T15:00:00Z", "created_by": "Andy",
            "source_type": "bulk", "reversal_of_batch_id": None,
        }
        movements = pd.DataFrame([
            {
                **common, "batch_id": "pink-m",
                "category": "彩色短袖", "brand": "Haloo",
                "material": "180g", "color": "粉色", "size": "M",
            },
            {
                **common, "batch_id": "pink-l",
                "category": "彩色短袖", "brand": "Haloo",
                "material": "180g", "color": "粉色", "size": "L",
            },
            {
                **common, "batch_id": "green-m",
                "category": "彩色短袖", "brand": "Haloo",
                "material": "180g", "color": "绿色", "size": "M",
            },
        ])
        history_data = (movements, pd.DataFrame(), pd.DataFrame())

        filtered, _, _ = filter_inventory_history_data(
            history_data, "彩色短袖", [], [], ["粉色"], ["M"],
        )

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered.iloc[0]["color"], "粉色")
        self.assertEqual(filtered.iloc[0]["size"], "M")


if __name__ == "__main__":
    unittest.main()
