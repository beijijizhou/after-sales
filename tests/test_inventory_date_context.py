from datetime import date
import unittest

from ui.inventory.stock.table import build_inventory_date_context


class InventoryDateContextTests(unittest.TestCase):
    def test_historical_snapshot_never_reports_stale_ledger(self):
        result = build_inventory_date_context(
            date(2026, 8, 7), date(2026, 8, 2), is_historical=True
        )

        self.assertEqual(result["label"], "历史库存日期")
        self.assertEqual(result["stale_days"], 0)
        self.assertIn("历史库存快照", result["message"])

    def test_current_view_uses_latest_ledger_change_for_freshness(self):
        result = build_inventory_date_context(
            date(2026, 8, 7), date(2026, 8, 2), is_historical=False
        )

        self.assertEqual(result["label"], "库存账最后变动")
        self.assertEqual(result["stale_days"], 5)
        self.assertEqual(result["message"], "")

    def test_yesterday_is_not_stale_before_new_york_7pm(self):
        result = build_inventory_date_context(
            date(2026, 8, 10), date(2026, 8, 9),
            is_historical=False, current_hour=18,
        )

        self.assertEqual(result["stale_days"], 0)

    def test_yesterday_becomes_stale_at_new_york_7pm(self):
        result = build_inventory_date_context(
            date(2026, 8, 10), date(2026, 8, 9),
            is_historical=False, current_hour=19,
        )

        self.assertEqual(result["stale_days"], 1)

    def test_older_ledger_is_stale_even_before_7pm(self):
        result = build_inventory_date_context(
            date(2026, 8, 10), date(2026, 8, 8),
            is_historical=False, current_hour=10,
        )

        self.assertEqual(result["stale_days"], 2)


if __name__ == "__main__":
    unittest.main()
