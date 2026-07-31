import unittest
from datetime import date

from db.inventory.operations.outbound_audit import (
    load_uv_daily_consumption_total,
)


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, data):
        self.data = data
        self.filters = []

    def select(self, *_args):
        return self

    def eq(self, field, value):
        self.filters.append(("eq", field, value))
        return self

    def like(self, field, value):
        self.filters.append(("like", field, value))
        return self

    def execute(self):
        return _Response(self.data)


class _Supabase:
    def __init__(self, data):
        self.query = _Query(data)

    def table(self, name):
        self.table_name = name
        return self.query


class UVDailyStatusTests(unittest.TestCase):
    def test_sums_only_uv_daily_deductions(self):
        client = _Supabase([
            {"quantity_change": -44},
            {"quantity_change": -5},
            {"quantity_change": 10},
        ])

        total = load_uv_daily_consumption_total(
            client, date(2026, 7, 30)
        )

        self.assertEqual(total, 49)
        self.assertEqual(client.table_name, "inventory_movements")
        self.assertIn(
            ("eq", "movement_date", "2026-07-30"),
            client.query.filters,
        )
        self.assertIn(
            ("like", "reason", "Google Sheets UV每日消耗｜%"),
            client.query.filters,
        )


if __name__ == "__main__":
    unittest.main()
