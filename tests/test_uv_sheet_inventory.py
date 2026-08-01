import unittest
from datetime import date

from automation.sync.uv_sheet_inventory import (
    load_daily_product_usage,
    load_daily_summary,
)
from automation.sync.google_sheets import GoogleSheetsClient


class FakeSheets:
    def list_sheets(self, _spreadsheet_id):
        return [
            {"title": "0430"},
            {"title": "0501"},
            {"title": "0502"},
            {"title": "0704"},
            {"title": "说明"},
        ]

    def batch_get_values(self, _spreadsheet_id, ranges):
        self.requested_ranges = ranges
        return {
            cell_range: (
                [["Tie_yuan_2020", 120]]
                if "0501" in cell_range
                else [["Tie_yuan_2020", 0]]
            )
            for cell_range in ranges
        }


class UVSheetInventoryTests(unittest.TestCase):
    def test_lists_all_spreadsheets_in_shared_folder(self):
        client = GoogleSheetsClient({
            "client_email": "test@example.com",
            "private_key": "unused",
        })
        captured = {}

        def request(method, url, **kwargs):
            captured.update(method=method, url=url, kwargs=kwargs)
            return {
                "files": [{
                    "id": "sheet-1", "name": "UV每日订单",
                    "webViewLink": "https://docs.google.com/spreadsheets/d/sheet-1",
                }]
            }

        client._request = request

        result = client.list_spreadsheets_in_folder("folder-1")

        self.assertEqual(result[0]["id"], "sheet-1")
        self.assertEqual(captured["method"], "GET")
        self.assertIn("'folder-1' in parents", captured["kwargs"]["params"]["q"])

    def test_reads_only_requested_date_tabs_and_product(self):
        sheets = FakeSheets()
        result = load_daily_product_usage(
            sheets,
            "spreadsheet",
            "Tie_yuan_2020",
            date(2026, 5, 1),
            date(2026, 5, 2),
        )

        self.assertEqual(result, {date(2026, 5, 1): 120})

    def test_supports_date_based_summary_ranges(self):
        sheets = FakeSheets()
        load_daily_product_usage(
            sheets,
            "spreadsheet",
            "Tie_1530",
            date(2026, 5, 1),
            date(2026, 7, 4),
            "M17:N30",
            [(date(2026, 7, 4), "P16:Q40")],
        )

        self.assertIn("'0501'!M17:N30", sheets.requested_ranges)
        self.assertIn("'0704'!P16:Q40", sheets.requested_ranges)

    def test_loads_all_positive_products_for_one_day(self):
        class DailySheets:
            def batch_get_values(self, _spreadsheet_id, ranges):
                return {
                    ranges[0]: [
                        ["材质", "数量"],
                        ["Tie_2030", 2300],
                        ["Tie_1040", 0],
                        ["Lv_2030", "1793"],
                        ["总计", 4093],
                    ]
                }

        result = load_daily_summary(
            DailySheets(), "spreadsheet", date(2026, 7, 30)
        )

        self.assertEqual(
            result, {"Tie_2030": 2300, "Lv_2030": 1793}
        )

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
