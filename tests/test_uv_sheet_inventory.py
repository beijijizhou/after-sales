import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from automation.sync.uv_sheet_inventory import (
    load_daily_product_usage,
    load_daily_summary,
    load_monthly_sku_summary,
)
from automation.sync.google_sheets import (
    GoogleSheetsClient,
    resolve_service_account_info,
)


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
    def test_resolves_service_account_from_environment_first(self):
        env_json = (
            '{"client_email":"env@example.com","private_key":"env-key"}'
        )
        with patch.dict(
            "os.environ",
            {"GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON": env_json},
            clear=False,
        ):
            info, source = resolve_service_account_info()

        self.assertEqual(source, "env")
        self.assertEqual(info["client_email"], "env@example.com")

    def test_resolves_service_account_from_secrets_when_env_missing(self):
        secrets_json = (
            '{"client_email":"secrets@example.com","private_key":"secret-key"}'
        )

        class Secrets(dict):
            def get(self, key, default=None):
                return super().get(key, default)

        with patch.dict(
            "os.environ",
            {"GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON": ""},
            clear=False,
        ):
            info, source = resolve_service_account_info(
                secrets=Secrets({
                    "GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON": secrets_json
                })
            )

        self.assertEqual(source, "secrets")
        self.assertEqual(info["client_email"], "secrets@example.com")

    def test_resolves_service_account_from_named_secrets_table(self):
        with patch.dict(
            "os.environ",
            {"GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON": ""},
            clear=False,
        ):
            info, source = resolve_service_account_info(
                secrets={
                    "google_sheets_service_account": {
                        "type": "service_account",
                        "client_email": "reader@example.com",
                        "private_key": "private-key",
                    }
                },
                credential_path="/path/that/does/not/exist.json",
            )

        self.assertEqual(source, "secrets.google_sheets_service_account")
        self.assertEqual(info["client_email"], "reader@example.com")

    def test_resolves_service_account_from_file_when_other_sources_missing(self):
        with TemporaryDirectory() as temp_dir:
            credential_path = Path(temp_dir) / "google-service-account.json"
            credential_path.write_text(
                '{"client_email":"file@example.com","private_key":"file-key"}',
                encoding="utf-8",
            )
            with patch.dict(
                "os.environ",
                {"GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON": ""},
                clear=False,
            ):
                info, source = resolve_service_account_info(
                    secrets={},
                    credential_path=credential_path,
                )

        self.assertEqual(source, "file")
        self.assertEqual(info["client_email"], "file@example.com")

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

    def test_loads_monthly_sku_summary_and_marks_missing_days(self):
        class MonthlySheets:
            def list_sheets(self, _spreadsheet_id):
                return [
                    {"title": "0701"},
                    {"title": "0702"},
                    {"title": "说明"},
                ]

            def batch_get_values(self, _spreadsheet_id, ranges):
                result = {}
                for cell_range in ranges:
                    if "0701" in cell_range and "A1:K1200" in cell_range:
                        result[cell_range] = [
                            ["平台", "批次号", "序列号", "操作人", "材质", "手机型号", "型号", "材质", "数量(件)", "进度", "备注"],
                            ["SDS1", "1", "1", "E", "Tie_2030", "", "", "", "10", "完成", ""],
                            ["SDS1", "2", "2", "E", "", "", "", "", "99", "完成", ""],
                        ]
                    elif "0702" in cell_range and "A1:K1200" in cell_range:
                        result[cell_range] = [
                            ["平台", "批次号", "序列号", "操作人", "材质", "手机型号", "型号", "材质", "数量(件)", "进度", "备注"],
                            ["SDS1", "3", "1", "E", "Tie_2030", "", "", "", "20", "完成", ""],
                            ["SDS1", "4", "2", "E", "Tie_1040", "", "", "", "3", "完成", ""],
                            ["SDS1", "5", "3", "E", "Tie_1040", "", "", "", "8", "暂停", ""],
                        ]
                    else:
                        result[cell_range] = []
                return result

        daily_df, sku_df, missing_dates = load_monthly_sku_summary(
            MonthlySheets(), "spreadsheet", 2026, 7
        )

        self.assertEqual(
            daily_df[["sheet_name", "total_quantity"]].to_dict("records"),
            [
                {"sheet_name": "0701", "total_quantity": 10},
                {"sheet_name": "0702", "total_quantity": 23},
            ],
        )
        self.assertEqual(
            sku_df.to_dict("records"),
            [
                {"sku": "Tie_1040", "total_quantity": 3},
                {"sku": "Tie_2030", "total_quantity": 30},
            ],
        )
        self.assertEqual(missing_dates[0].date().isoformat(), "2026-07-03")

    def test_monthly_summary_skips_non_completed_or_invalid_rows(self):
        class MonthlySheets:
            def list_sheets(self, _spreadsheet_id):
                return [{"title": "0701"}]

            def batch_get_values(self, _spreadsheet_id, ranges):
                return {
                    ranges[0]: [
                        ["平台", "批次号", "序列号", "操作人", "材质", "手机型号", "型号", "材质", "数量(件)", "进度", "备注"],
                        ["SDS1", "1", "1", "E", "Tie_2030", "", "", "", "10", "完成", ""],
                        ["SDS1", "2", "2", "E", "Tie_2030", "", "", "", "8", "作废", ""],
                        ["SDS1", "3", "3", "E", "Tie_1040", "", "", "", "", "完成", ""],
                    ]
                }

        daily_df, sku_df, missing_dates = load_monthly_sku_summary(
            MonthlySheets(), "spreadsheet", 2026, 7
        )

        self.assertEqual(int(daily_df.iloc[0]["total_quantity"]), 10)
        self.assertEqual(
            sku_df.to_dict("records"),
            [{"sku": "Tie_2030", "total_quantity": 10}],
        )
        self.assertEqual(len(missing_dates), 30)

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
