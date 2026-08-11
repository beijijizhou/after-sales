from datetime import date, datetime
import hashlib
import hmac
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd

from automation.api.humbird import build_production_item_payload
from automation.api.humbird.client import (
    _deduplicate_rows,
    _normalize_api_result,
    fetch_humbird_production_records,
)
from automation.api.humbird.http_client import (
    HumbirdAuthenticationError,
    _response_data,
    _signed_headers,
    fetch_humbird_production_records_http,
)
from automation.production import load_production_data
from utils.erp.humbird_parser import parse_humbird_records


class HumbirdApiTests(unittest.TestCase):
    @patch("automation.api.humbird.client.fetch_humbird_production_records_http")
    def test_legacy_humbird_entrypoint_is_api_only(self, fetch):
        fetch.return_value = [{"code": "item-1"}]
        result = fetch_humbird_production_records(
            "Haloo",
            date(2026, 8, 10),
            date(2026, 8, 10),
            credentials={"token": "shared-token"},
        )
        self.assertEqual(result, [{"code": "item-1"}])
        fetch.assert_called_once()

    def test_legacy_humbird_entrypoint_never_falls_back_to_chrome(self):
        with self.assertRaisesRegex(ValueError, "服务器不会启动 Chrome"):
            fetch_humbird_production_records(
                "Haloo",
                date(2026, 8, 10),
                date(2026, 8, 10),
            )

    def test_direct_api_signature_uses_token_without_browser(self):
        with (
            patch("automation.api.humbird.http_client.time.time", return_value=1.5),
            patch(
                "automation.api.humbird.http_client.random.randint",
                return_value=12,
            ),
        ):
            headers = _signed_headers("POST", '{"page":1}', "secret")

        source = "".join(sorted(["1500", "12", "", '{"page":1}']))
        expected = hmac.new(
            b"secret", source.encode(), hashlib.sha256
        ).hexdigest()
        self.assertEqual(headers["Authorization"], "Bearer secret")
        self.assertEqual(headers["sign"], expected)

    def test_direct_api_reports_expired_token_without_opening_browser(self):
        response = type("Response", (), {"status_code": 401})()

        with self.assertRaises(HumbirdAuthenticationError):
            _response_data(response, "Haloo")

    @patch("automation.api.humbird.http_client.requests.Session")
    def test_direct_api_sends_json_body_with_requests_data(self, session_type):
        response = session_type.return_value.post.return_value
        response.status_code = 200
        response.json.return_value = {
            "result_code": "200",
            "data": {"list": [], "total": 0},
        }
        refresh = session_type.return_value.put.return_value
        refresh.status_code = 200
        refresh.json.return_value = {"result_code": "200", "data": True}

        rows = fetch_humbird_production_records_http(
            "Haloo",
            date(2026, 8, 8),
            date(2026, 8, 8),
            {"token": "secret"},
        )

        self.assertEqual(rows, [])
        call = session_type.return_value.post.call_args
        self.assertIn('"page":1', call.kwargs["data"])
        self.assertNotIn("content", call.kwargs)

    @patch("automation.production.fetch_humbird_production_records_http")
    def test_humbird_platform_uses_direct_http_api(self, fetch):
        fetch.return_value = [{
            "code": "item-1",
            "production_order_id": "order-1",
            "style_name": "多色短袖T恤",
            "blank_product_name": "成人短袖T恤",
            "color": "绿色",
            "size": "L",
            "qty": 1,
            "status_name": "已生产",
            "process_route_name": "180g",
            "begin_production_time": 1786334400000,
        }]

        result = load_production_data(
            "Haloo",
            date(2026, 8, 10),
            date(2026, 8, 10),
            credentials={"token": "saved-token"},
        )

        fetch.assert_called_once()
        self.assertIn("直接 API", result.source)
        self.assertIsInstance(result.data, pd.DataFrame)

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

    def test_normalizes_wrapped_api_response(self):
        result = _normalize_api_result({
            "code": 0,
            "data": {"result": {"list": [{"code": "A"}], "total": 1}},
        })

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["list"][0]["code"], "A")

    def test_deduplicates_shifted_pages_by_production_item_code(self):
        rows = _deduplicate_rows([
            {"code": "A", "qty": 1},
            {"code": "B", "qty": 1},
            {"code": "A", "qty": 1},
            {"qty": 1},
            {"qty": 1},
        ])

        self.assertEqual([row.get("code") for row in rows], [
            "A", "B", None, None,
        ])

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
