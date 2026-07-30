import unittest
from datetime import date

from ui.inventory.container.week import (
    selected_week_bounds,
    week_bounds,
)


class ContainerWeekTests(unittest.TestCase):
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
