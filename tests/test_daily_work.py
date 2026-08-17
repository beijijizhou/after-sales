import unittest
from pathlib import Path

import pandas as pd

from ui.daily_work.models import (
    build_daily_editor,
    completion_summary,
    editor_records,
    history_summary,
)
from utils.auth.constants import NAV_SECTIONS, PAGE_ACCESS, ROLE_PERMISSIONS


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DailyWorkTests(unittest.TestCase):
    def setUp(self):
        self.tasks = pd.DataFrame([
            {"id": "daily", "section": "固定", "task_name": "每日检查", "task_kind": "daily"},
            {"id": "needed", "section": "临时", "task_name": "处理异常", "task_kind": "as_needed"},
        ])

    def test_editor_defaults_daily_pending_and_optional_not_applicable(self):
        editor = build_daily_editor(self.tasks, pd.DataFrame())

        self.assertEqual(editor["状态"].tolist(), ["待处理", "不适用"])

    def test_saved_records_override_defaults_and_round_trip(self):
        saved = pd.DataFrame([
            {"task_id": "daily", "status": "completed", "note": "已核对"},
        ])
        editor = build_daily_editor(self.tasks, saved)

        self.assertEqual(editor.iloc[0]["状态"], "已完成")
        self.assertEqual(editor.iloc[0]["备注"], "已核对")
        records = editor_records(editor)
        self.assertEqual(records[0]["status"], "completed")
        self.assertEqual(records[0]["task_name"], "每日检查")

    def test_completion_rate_excludes_not_applicable(self):
        editor = build_daily_editor(self.tasks, pd.DataFrame([
            {"task_id": "daily", "status": "completed", "note": ""},
        ]))

        self.assertEqual(completion_summary(editor)["rate"], 100)

    def test_history_is_batch_first_by_business_date(self):
        days = pd.DataFrame([
            {"id": "day-1", "work_date": "2026-08-16", "summary": "完成重点工作"},
        ])
        records = pd.DataFrame([
            {"day_id": "day-1", "status": "completed"},
            {"day_id": "day-1", "status": "pending"},
        ])

        summary = history_summary(days, records)

        self.assertEqual(summary.iloc[0]["已完成"], 1)
        self.assertEqual(summary.iloc[0]["待处理"], 1)
        self.assertEqual(summary.iloc[0]["完成率"], 50)

    def test_daily_work_follows_after_sales_full_access_rule(self):
        self.assertEqual(PAGE_ACCESS["daily_work"], "can_view_daily_work")
        self.assertIn("can_view_daily_work", ROLE_PERMISSIONS["admin"])
        self.assertIn("can_view_daily_work", ROLE_PERMISSIONS["after_sales"])
        section = next(items for title, items in NAV_SECTIONS if title == "日常管理")
        self.assertEqual(section, [("daily_work", "每日工作", "pages/17_每日工作.py")])

    def test_migration_seeds_andy_account_without_hardcoding_ui_owner(self):
        migration = (PROJECT_ROOT / "sql/personal_work/01_daily_work.sql").read_text()
        page = (PROJECT_ROOT / "ui/daily_work/page.py").read_text()
        self.assertIn("select 'a'", migration)
        self.assertIn('user.get("username")', page)
        self.assertNotIn('owner = "a"', page)


if __name__ == "__main__":
    unittest.main()
