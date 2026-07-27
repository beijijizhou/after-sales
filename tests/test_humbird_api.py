from datetime import date, datetime
import unittest
from zoneinfo import ZoneInfo

from automation.api.humbird import build_production_item_payload
from utils.erp.humbird_parser import parse_humbird_records


class HumbirdApiTests(unittest.TestCase):
    def test_payload_uses_new_york_production_time(self):
        payload = build_production_item_payload(
            date(2026, 7, 25),
            date(2026, 7, 25),
        )

        expected_start = datetime(
            2026, 7, 25, tzinfo=ZoneInfo("America/New_York")
        )
        self.assertEqual(payload["begin_production_time"], {
            "from": str(int(expected_start.timestamp() * 1000)),
            "to": str(int(
                expected_start.replace(
                    hour=23, minute=59, second=59, microsecond=999999
                ).timestamp() * 1000
            )),
        })
        self.assertEqual(payload["status"], [])
        self.assertEqual(payload["page_size"], 5000)

    def test_parser_maps_humbird_record_to_inventory_columns(self):
        data = parse_humbird_records(
            [{
                "code": "BDXGLY3-1",
                "production_order_id": "975172182705478445",
                "style_name": "棉T恤",
                "blank_product_code": "HI-10404",
                "blank_product_name": "男款双面短袖T恤",
                "color": "白色",
                "size": "XL",
                "qty": 1,
                "status_name": "已生产",
                "process_route_name": "CVC面料",
                "production_batch_code": "607251529034",
                "begin_production_time": 1784964566000,
                "finish_production_time": 1784998893000,
                "created": 1784950383000,
            }],
            "Haloo",
        )

        self.assertEqual(data.loc[0, "生产项编码"], "BDXGLY3-1")
        self.assertEqual(data.loc[0, "数量"], 1)
        self.assertEqual(data.loc[0, "运营商"], "Haloo")
        self.assertEqual(
            str(data.loc[0, "开始时间"]),
            "2026-07-25 03:29:26",
        )


if __name__ == "__main__":
    unittest.main()
