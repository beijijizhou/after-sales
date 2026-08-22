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
from ui.after_sales_hotstamp.models import (
    build_daily_person_balance,
    build_person_summary,
    build_weekly_person_special_mix,
    build_weekly_platform_allocation,
    build_weekly_platform_summary,
    prepare_comparison,
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
    def test_weekly_platform_allocation_and_special_mix_percentages(self):
        source = pd.DataFrame([
            _comparison(
                "2026-08-17", "甲", "Haloo", 60, 60, 70,
                entries=60, hoodie=30, multi_press=12,
            ),
            _comparison(
                "2026-08-18", "乙", "Haloo", 40, 40, 45,
                entries=40, hoodie=10, multi_press=8,
            ),
            _comparison(
                "2026-08-19", "甲", "汉森", 20, 20, 20,
                entries=20, hoodie=0, multi_press=0,
            ),
            _comparison(
                "2026-08-20", "乙", "汉森", 20, 20, 24,
                entries=20, hoodie=20, multi_press=5,
            ),
        ])
        comparison = prepare_comparison(source)
        allocation = build_weekly_platform_allocation(comparison, 10)
        haloo = allocation[allocation["platform"] == "Haloo"].set_index(
            "hotstamp_person"
        )

        self.assertEqual(haloo.loc["甲", "order_share_percent"], 60.0)
        self.assertEqual(haloo.loc["甲", "expected_share_percent"], 50.0)
        self.assertEqual(haloo.loc["甲", "allocation_status"], "需关注")
        self.assertEqual(
            haloo.loc["甲", "hoodie_allocation_share_percent"], 75.0
        )

        summary = build_weekly_platform_summary(allocation, 10).set_index(
            "platform"
        )
        self.assertEqual(summary.loc["Haloo", "order_share_spread"], 20.0)
        mix = build_weekly_person_special_mix(comparison).set_index(
            "hotstamp_person"
        )
        self.assertEqual(mix.loc["甲", "hansen_ratio_percent"], 25.0)

    def test_surfaces_balance_and_system_differences(self):
        source = pd.DataFrame([
            _comparison("2026-08-17", "甲", "Haloo", 100, 95, 100),
            _comparison("2026-08-17", "乙", "Haloo", 50, 60, 60),
            _comparison("2026-08-18", "甲", "Haloo", 80, 80, 80),
            _comparison("2026-08-18", "乙", "Haloo", 80, 0, 0),
            _comparison("2026-08-18", "未填写烫印人员", "S2B", 20, 0, 0),
            _comparison("2026-08-18", "丙", "S2B", 0, 20, 20),
        ])
        comparison = prepare_comparison(source)
        daily = build_daily_person_balance(comparison, tolerance_percent=10)
        people = build_person_summary(daily, tolerance_percent=10)

        first_day = daily[daily["business_date"] == date(2026, 8, 17)]
        self.assertEqual(set(first_day["balance_status"]), {"偏差明显"})
        self.assertEqual(
            comparison.iloc[3]["match_status"], "系统无记录"
        )
        person = people.set_index("hotstamp_person").loc["乙"]
        self.assertEqual(person["scan_gap"], 70)
        self.assertEqual(person["unbalanced_days"], 1)
        statuses = daily.set_index("hotstamp_person")["balance_status"]
        self.assertEqual(statuses.loc["未填写烫印人员"], "人员缺失")
        self.assertEqual(statuses.loc["丙"], "表格无登记")


class GoogleDriveTreeTests(unittest.TestCase):
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


def _comparison(
    day, person, platform, film, scans, pieces,
    entries=None, hoodie=0, multi_press=0,
):
    return {
        "business_date": day,
        "hotstamp_person": person,
        "platform": platform,
        "film_quantity": film,
        "system_scan_count": scans,
        "system_piece_count": pieces,
        "hoodie_film_quantity": hoodie,
        "hoodie_entry_count": hoodie,
        "multi_press_quantity": multi_press,
        "multi_press_entry_count": multi_press,
        "source_entry_count": entries if entries is not None else (1 if film else 0),
    }


if __name__ == "__main__":
    unittest.main()
