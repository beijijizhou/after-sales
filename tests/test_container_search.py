import unittest
from pathlib import Path

import pandas as pd

from ui.inventory.container.search import (
    build_container_search_choices,
    filter_editable_container_search_rows,
    filter_container_search_choices,
    get_container_search_action,
)


class ContainerSearchTests(unittest.TestCase):
    def test_search_section_routes_posted_edits_to_inventory_batch(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "ui/inventory/container/search.py"
        ).read_text()

        self.assertIn('st.subheader("查找与修改货柜")', source)
        self.assertIn("这里只查找和修改仍在运输中的货柜", source)
        self.assertIn("不是当前剩余库存", source)
        self.assertIn("库存 → 批次修改与撤销", source)
        self.assertNotIn("render_posted_container_correction", source)

    def test_search_only_contains_containers_still_in_transit(self):
        rows = pd.DataFrame([
            {"container_key": "在途柜", "status": "在途"},
            {"container_key": "延迟柜", "status": "延迟"},
            {"container_key": "到柜", "status": "已到柜"},
            {"container_key": "入库柜", "status": "已入库"},
        ])

        result = filter_editable_container_search_rows(rows)

        self.assertEqual(
            result["container_key"].tolist(), ["在途柜", "延迟柜"]
        )

    def test_mixed_status_container_does_not_remain_in_search(self):
        rows = pd.DataFrame([
            {"container_key": "状态切换柜", "status": "在途"},
            {"container_key": "状态切换柜", "status": "已到柜"},
        ])

        result = filter_editable_container_search_rows(rows)

        self.assertTrue(result.empty)

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

    def test_nan_physical_number_is_not_displayed_as_container_number(self):
        rows = pd.DataFrame([{
            "container_key": "朱总第十七柜", "container_no": float("nan"),
            "status": "在途", "actual_arrival_date": None,
            "expected_arrival_date": "2026-10-09", "department": "UV",
            "category": "铁板画", "quantity": 105200,
            "note": "朱总第十七柜",
        }])

        choices = build_container_search_choices(rows)

        self.assertTrue(choices["朱总第十七柜"].startswith("朱总第十七柜｜在途"))
        self.assertNotIn("nan", choices["朱总第十七柜"].casefold())

    def test_search_matches_physical_number_and_business_remark(self):
        rows = pd.DataFrame([
            {
                "container_key": "14柜", "container_no": "TRHU5477320",
                "status": "在途", "actual_arrival_date": None,
                "expected_arrival_date": "2026-08-17", "department": "UV",
                "category": "铁板画", "quantity": 55000,
                "note": "第十四柜；白铁2030",
            },
            {
                "container_key": "15柜", "container_no": "WHSU6109931",
                "status": "在途", "actual_arrival_date": None,
                "expected_arrival_date": "2026-09-12", "department": "UV",
                "category": "铁板画", "quantity": 75000,
                "note": "朱总第十五柜",
            },
        ])
        choices = build_container_search_choices(rows)

        by_number = filter_container_search_choices(
            rows, choices, " trhu 5477320 "
        )
        by_remark = filter_container_search_choices(
            rows, choices, "朱总第十五柜"
        )

        self.assertEqual(list(by_number), ["14柜"])
        self.assertEqual(list(by_remark), ["15柜"])

    def test_search_returns_empty_mapping_when_container_is_absent(self):
        rows = pd.DataFrame([{
            "container_key": "14柜", "container_no": "TRHU5477320",
            "status": "在途", "actual_arrival_date": None,
            "expected_arrival_date": "2026-08-17", "department": "UV",
            "category": "铁板画", "quantity": 55000, "note": "第十四柜",
        }])
        choices = build_container_search_choices(rows)

        result = filter_container_search_choices(
            rows, choices, "COSU6502384810"
        )

        self.assertEqual(result, {})

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
