from datetime import date
import unittest

from db.inventory.core.queries import (
    load_latest_inventory_movement_date,
)


class QueryStub:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.data = rows

    def table(self, name):
        self.calls.append(("table", name))
        return self

    def select(self, columns):
        self.calls.append(("select", columns))
        return self

    def eq(self, column, value):
        self.calls.append(("eq", column, value))
        return self

    def in_(self, column, values):
        self.calls.append(("in", column, values))
        return self

    def order(self, column, desc=False):
        self.calls.append(("order", column, desc))
        return self

    def limit(self, value):
        self.calls.append(("limit", value))
        return self

    def execute(self):
        return self


class LatestInventoryMovementTests(unittest.TestCase):
    def test_uses_latest_movement_in_selected_materials(self):
        query = QueryStub([{"movement_date": "2026-07-28"}])

        result = load_latest_inventory_movement_date(
            query,
            "DTF",
            "黑白短袖",
            materials=["160g", "180g", "CVC"],
        )

        self.assertEqual(result, date(2026, 7, 28))
        self.assertIn(
            ("in", "material", ["160g", "180g", "CVC"]),
            query.calls,
        )
        self.assertIn(("order", "movement_date", True), query.calls)

    def test_empty_scope_has_no_movement_date(self):
        query = QueryStub([])

        result = load_latest_inventory_movement_date(query, "UV")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
