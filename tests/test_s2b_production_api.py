from datetime import date
import unittest
from unittest.mock import Mock, patch

from automation.api.s2b.client import (
    fetch_s2b_production_records,
    new_york_production_bounds,
)
from automation.api.s2b.parser import parse_s2b_production_records


class S2BProductionApiTests(unittest.TestCase):
    def test_new_york_day_uses_full_local_day(self):
        start, end = new_york_production_bounds(
            date(2026, 8, 2), date(2026, 8, 2)
        )

        self.assertEqual(start.strftime("%Y-%m-%d %H:%M:%S %Z"),
                         "2026-08-02 00:00:00 EDT")
        self.assertEqual(end.strftime("%Y-%m-%d %H:%M:%S %Z"),
                         "2026-08-02 23:59:59 EDT")

    @patch("automation.api.s2b.client.requests.Session")
    def test_api_reads_every_page_with_production_time(self, session_class):
        first = Mock()
        first.status_code = 200
        first.json.return_value = {
            "data": {
                "data": [{"id": 1}], "total": 2,
                "last_page": 2, "current_page": 1,
            }
        }
        second = Mock()
        second.status_code = 200
        second.json.return_value = {
            "data": {
                "data": [{"id": 2}], "total": 2,
                "last_page": 2, "current_page": 2,
            }
        }
        session_class.return_value.get.side_effect = [first, second]

        result = fetch_s2b_production_records(
            date(2026, 8, 2), date(2026, 8, 2), {"token": "valid"}
        )

        self.assertEqual([row["id"] for row in result], [1, 2])
        calls = session_class.return_value.get.call_args_list
        self.assertEqual(calls[0].kwargs["params"]["page"], 1)
        self.assertEqual(calls[1].kwargs["params"]["page"], 2)
        self.assertEqual(
            calls[0].kwargs["params"]["production_at_before"],
            "2026-08-02 00:00:00",
        )
        self.assertEqual(
            calls[0].kwargs["params"]["production_at_after"],
            "2026-08-02 23:59:59",
        )

    def test_api_rows_use_existing_colored_tshirt_catalog(self):
        result = parse_s2b_production_records([{
            "id": 99,
            "order_code": "ORDER-1",
            "order_item_code": "ORDER-1-1",
            "basic_product_name": "180g成人烫画短袖T恤",
            "color_name": "Red",
            "size_name": "L",
            "num": 3,
            "order_status_text": "已生产",
            "product_batch_number": "B1",
            "production_at": "2026-08-02 15:30:00",
        }])

        row = result.iloc[0]
        self.assertEqual(row["运营商"], "S2B")
        self.assertEqual(row["品类"], "彩色短袖")
        self.assertEqual(row["颜色"], "红色")
        self.assertEqual(row["尺码"], "L")
        self.assertEqual(row["数量"], 3)
        self.assertEqual(
            row["数据口径"], "S2B 账单生产时间（纽约）"
        )


if __name__ == "__main__":
    unittest.main()
