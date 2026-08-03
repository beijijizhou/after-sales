import unittest
from datetime import date

from ui.inventory.container.week import (
    merge_current_week_with_overdue,
    selected_week_bounds,
    week_bounds,
)
import pandas as pd


class ContainerWeekTests(unittest.TestCase):
    def test_current_week_includes_overdue_unconfirmed_containers(self):
        current = pd.DataFrame([{
            "id": "current", "container_key": "C2",
            "expected_arrival_date": "2026-08-04",
        }])
        overdue = pd.DataFrame([{
            "id": "overdue", "container_key": "C1",
            "expected_arrival_date": "2026-07-28",
        }])

        result = merge_current_week_with_overdue(current, overdue)

        self.assertEqual(set(result["container_key"]), {"C1", "C2"})

    def test_current_week_starts_today(self):
        today = date(2026, 7, 30)
        current_start, current_end = week_bounds(today)

        start, end = selected_week_bounds(current_start, today)

        self.assertEqual(start, today)
        self.assertEqual(end, current_end)

    def test_future_week_keeps_full_week(self):
        today = date(2026, 7, 30)
        future_start = date(2026, 8, 3)

        start, end = selected_week_bounds(future_start, today)

        self.assertEqual(start, future_start)
        self.assertEqual(end, date(2026, 8, 9))


if __name__ == "__main__":
    unittest.main()
