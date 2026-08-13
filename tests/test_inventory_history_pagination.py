import unittest

from db.inventory.core.pagination import fetch_range_pages


class InventoryHistoryPaginationTests(unittest.TestCase):
    def test_reads_past_supabase_one_thousand_row_limit(self):
        source = [{"id": index} for index in range(1_446)]
        requests = []

        def fetch_page(start, end):
            requests.append((start, end))
            return source[start:end + 1]

        rows = fetch_range_pages(fetch_page, limit=10_000)

        self.assertEqual(len(rows), 1_446)
        self.assertEqual(requests, [(0, 999), (1000, 1999)])
        self.assertEqual(rows[-1]["id"], 1_445)

    def test_stops_at_requested_limit(self):
        source = [{"id": index} for index in range(3_000)]

        rows = fetch_range_pages(
            lambda start, end: source[start:end + 1], limit=1_250
        )

        self.assertEqual(len(rows), 1_250)
        self.assertEqual(rows[-1]["id"], 1_249)

    def test_zero_limit_does_not_query(self):
        called = False

        def fetch_page(_start, _end):
            nonlocal called
            called = True
            return []

        self.assertEqual(fetch_range_pages(fetch_page, limit=0), [])
        self.assertFalse(called)

    def test_none_limit_reads_until_last_page(self):
        source = [{"id": index} for index in range(1_001)]
        requests = []

        def fetch_page(start, end):
            requests.append((start, end))
            return source[start:end + 1]

        rows = fetch_range_pages(fetch_page, limit=None)

        self.assertEqual(len(rows), 1_001)
        self.assertEqual(requests, [(0, 999), (1000, 1999)])


if __name__ == "__main__":
    unittest.main()
