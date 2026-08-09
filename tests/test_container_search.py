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

    def test_business_remark_is_primary_and_container_number_is_secondary(self):
        rows = pd.DataFrame([{
            "container_key": "12柜",
            "container_no": "ZCSU7707166",
            "status": "未到货",
            "actual_arrival_date": None,
            "expected_arrival_date": "2026-08-04",
            "department": "UV",
            "category": "铁板画",
            "quantity": 145000,
            "note": "货柜汇总核对：表格第十柜；明细一致",
        }])

        choices = build_container_search_choices(rows)

        self.assertTrue(
            choices["12柜"].startswith("第十柜｜柜号 ZCSU7707166｜未到货")
        )

    def test_missing_physical_number_shows_only_business_remark(self):
        rows = pd.DataFrame([{
            "container_key": "朱总第十六柜",
            "container_no": "朱总第十六柜",
            "status": "在途",
            "actual_arrival_date": None,
            "expected_arrival_date": "2026-10-02",
            "department": "UV",
            "category": "铁板画",
            "quantity": 138900,
            "note": "实体柜号待补",
        }])

        choices = build_container_search_choices(rows)

        self.assertTrue(choices["朱总第十六柜"].startswith("朱总第十六柜｜在途"))
        self.assertNotIn("柜号", choices["朱总第十六柜"])

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
