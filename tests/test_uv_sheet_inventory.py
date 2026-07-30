import unittest
from datetime import date

from automation.sync.uv_sheet_inventory import (
    load_daily_product_usage,
)
from automation.sync.google_sheets import GoogleSheetsClient


class FakeSheets:
    def list_sheets(self, _spreadsheet_id):
        return [
            {"title": "0430"},
            {"title": "0501"},
            {"title": "0502"},
            {"title": "说明"},
        ]

    def batch_get_values(self, _spreadsheet_id, ranges):
        return {
            cell_range: (
                [["Tie_yuan_2020", 120]]
                if "0501" in cell_range
                else [["Tie_yuan_2020", 0]]
            )
            for cell_range in ranges
        }


class UVSheetInventoryTests(unittest.TestCase):
    def test_reads_only_requested_date_tabs_and_product(self):
        result = load_daily_product_usage(
            FakeSheets(),
            "spreadsheet",
            "Tie_yuan_2020",
            date(2026, 5, 1),
            date(2026, 5, 2),
        )

        self.assertEqual(result, {date(2026, 5, 1): 120})

    def test_google_sheets_client_writes_bounded_range(self):
        client = GoogleSheetsClient({
            "client_email": "test@example.com",
            "private_key": "unused",
        })
        client._access_token = "token"
        client._expires_at = 9_999_999_999
        captured = {}

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"updatedCells": 2}

        def request(method, url, **kwargs):
            captured.update(method=method, url=url, kwargs=kwargs)
            return Response()

        client.session.request = request
        result = client.update_values(
            "spreadsheet", "'同步状态'!A1:B1", [["完成", 120]]
        )

        self.assertEqual(result["updatedCells"], 2)
        self.assertEqual(captured["method"], "PUT")
        self.assertEqual(
            captured["kwargs"]["json"]["values"], [["完成", 120]]
        )


if __name__ == "__main__":
    unittest.main()
