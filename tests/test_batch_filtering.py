import unittest

import pandas as pd

from db.batches import filter_active_batch_records, reversed_record_ids


class BatchFilteringTests(unittest.TestCase):
    def setUp(self):
        self.records = pd.DataFrame([
            {
                "id": "active", "movement_type": "issue",
                "reversal_of_batch_id": None,
            },
            {
                "id": "original", "movement_type": "issue",
                "reversal_of_batch_id": None,
            },
            {
                "id": "undo", "movement_type": "reversal",
                "reversal_of_batch_id": "original",
            },
        ])

    def test_reversed_ids_are_derived_from_append_only_events(self):
        self.assertEqual(reversed_record_ids(self.records), {"original"})

    def test_active_filter_removes_original_and_reversal(self):
        result = filter_active_batch_records(
            self.records, type_column="movement_type"
        )

        self.assertEqual(result["id"].tolist(), ["active"])

    def test_inventory_movements_can_use_batch_id_as_identity(self):
        movements = pd.DataFrame([
            {"batch_id": "active", "reversal_of_batch_id": None},
            {"batch_id": "original", "reversal_of_batch_id": None},
            {"batch_id": "undo", "reversal_of_batch_id": "original"},
        ])

        result = filter_active_batch_records(
            movements, id_column="batch_id"
        )

        self.assertEqual(result["batch_id"].tolist(), ["active"])

    def test_legacy_records_without_reversal_column_remain_visible(self):
        records = pd.DataFrame([{"id": "legacy"}])

        result = filter_active_batch_records(records)

        self.assertEqual(result["id"].tolist(), ["legacy"])


if __name__ == "__main__":
    unittest.main()
