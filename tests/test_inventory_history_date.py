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


if __name__ == "__main__":
    unittest.main()
