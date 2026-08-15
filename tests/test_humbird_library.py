from datetime import date
import unittest

from humbird_erp import (
    HumbirdApiError,
    HumbirdClient,
    fetch_production_records,
)


class HumbirdLibraryTests(unittest.TestCase):
    def test_public_api_exposes_client_error_and_convenience_function(self):
        self.assertTrue(issubclass(HumbirdApiError, RuntimeError))
        self.assertTrue(callable(fetch_production_records))

    def test_client_reads_waybill_with_api_key(self):
        response = type("Response", (), {
            "status_code": 200,
            "raise_for_status": lambda self: None,
            "json": lambda self: {
                "code": 200,
                "result": {
                    "result_code": 200,
                    "data": {"track_number": "9400111899"},
                },
            },
        })()
        session = type("Session", (), {})()
        calls = []

        def post(url, **kwargs):
            calls.append((url, kwargs))
            return response

        session.post = post
        client = HumbirdClient("open-key", session=session)

        result = client.waybill("ORDER-1")

        self.assertEqual(result["track_number"], "9400111899")
        self.assertEqual(calls[0][1]["headers"]["x-api-key"], "open-key")
        self.assertEqual(
            calls[0][1]["json"],
            {"api_type": "logistics.waybill.get", "order_no": "ORDER-1"},
        )

    def test_client_accepts_existing_credentials_mapping(self):
        client = HumbirdClient({"api_key": "mapped-key"})
        self.assertEqual(client.api_key, "mapped-key")

    def test_production_query_rejects_more_than_thirty_days(self):
        client = HumbirdClient({"api_key": "open-key"})
        with self.assertRaisesRegex(ValueError, "最多查询 30 天"):
            client.production_items(date(2026, 7, 1), date(2026, 8, 1))


if __name__ == "__main__":
    unittest.main()
