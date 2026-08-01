import unittest

import pandas as pd

from ui.inventory.history.history_batches import (
    add_movement_batch_key,
    add_sku_batch_key,
)


class InventoryHistoryTimezoneTests(unittest.TestCase):
    def test_movement_time_is_displayed_in_new_york(self):
        source = pd.DataFrame([{
            "created_at": "2026-07-31T22:56:00+00:00",
            "movement_date": "2026-07-31",
            "quantity_change": -1,
            "reason": "每日出库",
            "created_by": "Andy",
            "department": "DTF",
            "category": "黑白短袖",
            "batch_id": "batch-1",
        }])

        result = add_movement_batch_key(source)

        self.assertEqual(result.loc[0, "recorded_key"], "2026-07-31 18:56")

    def test_sku_import_time_is_displayed_in_new_york(self):
        source = pd.DataFrame([{
            "created_at": "2026-07-31T22:56:00Z",
            "import_date": "2026-07-31",
            "initial_quantity": 1,
            "department": "DTF",
            "category": "黑白短袖",
        }])

        result = add_sku_batch_key(source)

        self.assertEqual(result.loc[0, "recorded_key"], "2026-07-31 18:56")


if __name__ == "__main__":
    unittest.main()
