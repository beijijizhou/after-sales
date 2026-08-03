import unittest

import pandas as pd

from ui.inventory.container.search import (
    build_container_search_choices,
    get_container_search_action,
)


class ContainerSearchTests(unittest.TestCase):
    def test_choices_are_unique_per_container(self):
        rows = pd.DataFrame([
            {
                "container_key": "26071701", "container_no": "26071701",
                "status": "已入库", "actual_arrival_date": "2026-07-31",
                "expected_arrival_date": "2026-07-29",
                "department": "DTF", "category": "黑白短袖",
                "quantity": 19008,
            },
            {
                "container_key": "26071701", "container_no": "26071701",
                "status": "已入库", "actual_arrival_date": "2026-07-31",
                "expected_arrival_date": "2026-07-29",
                "department": "DTF", "category": "黑白短袖",
                "quantity": 9316,
            },
        ])

        choices = build_container_search_choices(rows)

        self.assertEqual(list(choices), ["26071701"])
        self.assertIn("已入库", choices["26071701"])
        self.assertIn("2026-07-31", choices["26071701"])
        self.assertIn("DTF · 黑白短袖", choices["26071701"])
        self.assertIn("28,324 件", choices["26071701"])

    def test_in_transit_search_result_offers_arrival_action(self):
        rows = pd.DataFrame([{"status": "在途"}, {"status": "在途"}])
        self.assertEqual(get_container_search_action(rows), "arrival")

    def test_arrived_search_result_offers_posting_action(self):
        rows = pd.DataFrame([{"status": "已到柜"}])
        self.assertEqual(get_container_search_action(rows), "posting")

    def test_posted_search_result_is_completed(self):
        rows = pd.DataFrame([{"status": "已入库"}])
        self.assertEqual(get_container_search_action(rows), "completed")


if __name__ == "__main__":
    unittest.main()
