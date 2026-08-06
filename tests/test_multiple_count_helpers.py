import unittest
from datetime import date

from utils.multiple_count_helpers import refresh_multiple_counts


class FakeRpcCall:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class FakeSupabase:
    def __init__(self):
        self.calls = []

    def rpc(self, function_name, params):
        self.calls.append((function_name, params))
        return FakeRpcCall({"refreshed": True})


class MultipleCountHelperTests(unittest.TestCase):
    def test_refresh_uses_combined_incremental_database_function(self):
        supabase = FakeSupabase()

        result = refresh_multiple_counts(supabase, date(2026, 8, 4))

        self.assertEqual(result, {"refreshed": True})
        self.assertEqual(
            supabase.calls,
            [
                (
                    "refresh_barcode_multiple_counts",
                    {"target_date": "2026-08-04"},
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
