from datetime import date
import unittest

from db.inventory.container.repository import apply_container_filters
from ui.inventory.container.week import week_bounds, week_label


class QueryRecorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name, args))
            return self
        return record


class ContainerWeekTests(unittest.TestCase):
    def test_week_runs_monday_through_sunday(self):
        start, end = week_bounds(date(2026, 7, 29))

        self.assertEqual(start, date(2026, 7, 27))
        self.assertEqual(end, date(2026, 8, 2))

    def test_current_week_label_contains_dates_and_weekdays(self):
        start = date(2026, 7, 27)

        label = week_label(start, start)

        self.assertEqual(
            label,
            "本周｜07/27（周一）- 08/02（周日）",
        )

    def test_container_filters_are_applied_to_database_query(self):
        query = QueryRecorder()

        apply_container_filters(
            query,
            date(2026, 7, 27),
            date(2026, 8, 2),
            "DTF",
            "黑白短袖",
            ["未到货"],
            "expected_arrival_date",
            ["Haloo"],
            ["CVC"],
            ["黑"],
            ["L"],
        )

        self.assertIn(("eq", ("department", "DTF")), query.calls)
        self.assertIn(("in_", ("brand", ["Haloo"])), query.calls)
        self.assertIn(("in_", ("size", ["L"])), query.calls)


if __name__ == "__main__":
    unittest.main()
