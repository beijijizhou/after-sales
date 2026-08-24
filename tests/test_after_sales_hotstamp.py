import unittest
from contextlib import nullcontext
from datetime import date
from unittest.mock import Mock, patch

import pandas as pd

from automation.sync.after_sales_hotstamp.parser import (
    normalize_source_platform,
    parse_daily_rows,
    parse_week_start,
)
from automation.sync.after_sales_hotstamp.service import (
    load_hotstamp_film_previews,
)
from automation.sync.google_sheets import GoogleSheetsClient
from db.after_sales_hotstamp import load_hotstamp_manual_analysis
from ui.after_sales_hotstamp.models import (
    build_daily_manual_summary,
    build_person_manual_summary,
    build_platform_person_summary,
    build_weekly_manual_summary,
    prepare_manual_analysis,
)
from ui.after_sales_hotstamp.page import render_hotstamp_film_audit
from utils.auth.constants import NAV_SECTIONS, PAGE_ACCESS


class AfterSalesHotstampParserTests(unittest.TestCase):
    def test_parses_modern_and_legacy_weekly_rows(self):
        source = {"id": "file-1", "name": "08/17-08/23"}
        modern = [
            ["平台", "剪膜", "配衣", "数量", "卫衣", "多烫", "白板", "烫印人员", "质检人员"],
            ["haloo", "剪膜甲", "配衣甲", 12, False, 2, True, "烫印甲", "质检甲"],
            ["", "", "", "", False, "", False, "模板残留", ""],
        ]
        rows, invalid = parse_daily_rows(
            modern, source, "周一", date(2026, 8, 17)
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["platform"], "Haloo")
        self.assertEqual(rows[0]["film_quantity"], 12)
        self.assertEqual(rows[0]["source_row_number"], 2)
        self.assertEqual(len(invalid), 1)

        legacy = [
            ["平台", "剪膜人员", "数量", "卫衣", "多烫", "烫印人员", "质检人员"],
            ["7创", "剪膜乙", "8", False, "", "烫印乙", "质检乙"],
        ]
        rows, invalid = parse_daily_rows(
            legacy, source, "周二", date(2026, 8, 18)
        )
        self.assertFalse(invalid)
        self.assertEqual(rows[0]["platform"], "七创")
        self.assertEqual(rows[0]["matching_person"], "")

    def test_parses_week_year_from_file_created_time(self):
        self.assertEqual(
            parse_week_start("03/30-04/05", "2026-03-29T12:00:00Z"),
            date(2026, 3, 30),
        )
        self.assertEqual(normalize_source_platform("SDS-2"), "SDS2")

    def test_builds_batch_first_preview(self):
        class Sheets:
            def list_spreadsheets_in_tree(self, _folder_id):
                return [{
                    "id": "sheet-1", "name": "08/17-08/23",
                    "createdTime": "2026-08-17T00:00:00Z",
                    "modifiedTime": "2026-08-18T00:00:00Z",
                    "webViewLink": "https://example.test/sheet-1",
                }]

            def list_sheets(self, _spreadsheet_id):
                return [{"title": "周一"}, {"title": "说明"}]

            def batch_get_values(self, _spreadsheet_id, ranges):
                return {ranges[0]: [
                    ["平台", "剪膜", "配衣", "数量", "卫衣", "多烫", "白板", "烫印人员", "质检人员"],
                    ["haloo", "甲", "乙", 25, False, "", False, "丙", "丁"],
                ]}

        previews = load_hotstamp_film_previews(Sheets(), "folder")

        self.assertEqual(len(previews), 1)
        self.assertEqual(previews[0]["row_count"], 1)
        self.assertEqual(previews[0]["total_film_quantity"], 25)
        self.assertEqual(len(previews[0]["source_hash"]), 64)


class AfterSalesHotstampModelTests(unittest.TestCase):
    def test_summarizes_only_manual_registration_data(self):
        source = pd.DataFrame([
            _manual("2026-08-17", "甲", "Haloo", 60, 600, 30, 12),
            _manual("2026-08-18", "乙", "Haloo", 40, 400, 10, 8),
            _manual("2026-08-19", "甲", "汉森", 20, 200, 0, 0),
            _manual("2026-08-20", "乙", "汉森", 20, 200, 20, 5),
        ])
        rows = prepare_manual_analysis(source)
        weekly = build_weekly_manual_summary(rows).set_index("platform")
        self.assertEqual(weekly.loc["Haloo", "registration_share_percent"], 71.4)
        self.assertEqual(weekly.loc["Haloo", "hoodie_ratio_percent"], 40.0)

        platform_people = build_platform_person_summary(rows)
        haloo = platform_people[
            platform_people["platform"] == "Haloo"
        ].set_index("hotstamp_person")
        self.assertEqual(haloo.loc["甲", "registration_share_percent"], 60.0)

        people = build_person_manual_summary(rows).set_index("hotstamp_person")
        self.assertEqual(people.loc["甲", "hansen_ratio_percent"], 25.0)
        daily = build_daily_manual_summary(rows)
        self.assertEqual(int(daily["registration_count"].sum()), 140)

    def test_manual_analysis_pages_through_every_rpc_row(self):
        supabase = Mock()
        builder = Mock()
        supabase.rpc.return_value = builder
        builder.range.return_value = builder
        builder.execute.side_effect = [
            Mock(data=[{"business_date": "2026-08-01"}] * 1000),
            Mock(data=[{"business_date": "2026-08-02"}] * 3),
        ]

        result = load_hotstamp_manual_analysis(
            supabase, date(2026, 8, 1), date(2026, 8, 2)
        )

        self.assertEqual(len(result), 1003)
        self.assertEqual(
            [call.args for call in builder.range.call_args_list],
            [(0, 999), (1000, 1999)],
        )


class GoogleDriveTreeTests(unittest.TestCase):
    @patch("automation.sync.google_sheets.time.sleep")
    def test_retries_google_rate_limits(self, sleep):
        client = GoogleSheetsClient({
            "client_email": "test@example.com", "private_key": "unused"
        })
        client._token = lambda: "token"
        limited = Mock(status_code=429, headers={})
        success = Mock(status_code=200)
        success.json.return_value = {"files": []}
        client.session.request = Mock(side_effect=[limited, success])

        result = client._request("GET", "https://example.test")

        self.assertEqual(result, {"files": []})
        sleep.assert_called_once_with(1)

    def test_lists_spreadsheets_recursively(self):
        client = GoogleSheetsClient({
            "client_email": "test@example.com", "private_key": "unused"
        })
        items = {
            "root": [
                {"id": "current", "mimeType": "application/vnd.google-apps.spreadsheet"},
                {"id": "archive", "mimeType": "application/vnd.google-apps.folder"},
            ],
            "archive": [
                {"id": "old", "mimeType": "application/vnd.google-apps.spreadsheet"},
            ],
        }
        client.list_drive_items_in_folder = lambda folder_id: items[folder_id]

        result = client.list_spreadsheets_in_tree("root")

        self.assertEqual({item["id"] for item in result}, {"current", "old"})


class AfterSalesHotstampAccessTests(unittest.TestCase):
    def test_sidebar_uses_real_after_sales_child_navigation(self):
        section = next(
            items for title, items in NAV_SECTIONS if title == "售后查询"
        )

        self.assertEqual(
            [item[1] for item in section],
            ["订单与条码查询", "人工登记分析"],
        )
        self.assertEqual(
            PAGE_ACCESS["after_sales_manual_analysis"],
            "can_input_after_sales",
        )

    @patch("ui.after_sales_hotstamp.page.st.error")
    @patch("ui.after_sales_hotstamp.page.has_role", return_value=False)
    def test_other_roles_are_rejected(self, _has_role, error):
        render_hotstamp_film_audit(Mock(), "folder")

        error.assert_called_once_with("此功能仅对售后和管理员角色开放。")

    @patch("ui.after_sales_hotstamp.page.render_batch_history")
    @patch("ui.after_sales_hotstamp.page.render_sync_view")
    @patch("ui.after_sales_hotstamp.page.render_audit_view")
    @patch("ui.after_sales_hotstamp.page.st.tabs")
    @patch("ui.after_sales_hotstamp.page.has_role", return_value=True)
    def test_after_sales_or_admin_can_open_page(
        self, _has_role, tabs, _audit, _sync, _history
    ):
        tabs.return_value = [nullcontext(), nullcontext(), nullcontext()]

        render_hotstamp_film_audit(Mock(), "folder")

        tabs.assert_called_once()


def _manual(day, person, platform, registrations, film, hoodie, multi_press):
    return {
        "business_date": day,
        "hotstamp_person": person,
        "platform": platform,
        "registration_count": registrations,
        "film_quantity": film,
        "hoodie_registration_count": hoodie,
        "hoodie_film_quantity": hoodie * 10,
        "multi_press_registration_count": multi_press,
        "multi_press_quantity": multi_press,
        "white_board_registration_count": 0,
        "white_board_film_quantity": 0,
    }


if __name__ == "__main__":
    unittest.main()
