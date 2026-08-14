import unittest
from datetime import date

import pandas as pd

from db.inventory.core.snapshots import (
    filter_snapshot_to_active_skus,
    should_use_saved_snapshot,
)


class ActiveInventorySnapshotTests(unittest.TestCase):
    def test_today_uses_live_inventory_instead_of_saved_snapshot(self):
        today = date(2026, 8, 14)

        self.assertFalse(should_use_saved_snapshot(today, today))
        self.assertTrue(
            should_use_saved_snapshot(date(2026, 8, 13), today)
        )

    def test_inactive_snapshot_rows_are_hidden(self):
        snapshot = pd.DataFrame([
            _row("CHEPAI", 0),
            _row("2030", 7695),
        ])
        active = pd.DataFrame([_row("2030", 7695)])

        result = filter_snapshot_to_active_skus(snapshot, active)

        self.assertEqual(result["size"].tolist(), ["2030"])
        self.assertEqual(result["quantity"].tolist(), [7695])


def _row(size, quantity):
    return {
        "department": "UV", "category": "铁板画", "brand": "",
        "material": "铁牌", "color": "白", "size": size,
        "quantity": quantity,
    }


if __name__ == "__main__":
    unittest.main()
