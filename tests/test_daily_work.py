import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from db.daily_work import load_daily_work

from ui.daily_work.models import (
    build_daily_editor,
    completion_summary,
    editor_records,
    history_summary,
    style_status_table,
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

        self.assertEqual(
            editor["状态"].tolist(), ["🟡 待处理", "⚪ 不适用"]
        )

    def test_saved_records_override_defaults_and_round_trip(self):
        saved = pd.DataFrame([
            {"task_id": "daily", "status": "completed", "note": "已核对"},
        ])
        editor = build_daily_editor(self.tasks, saved)

        self.assertEqual(editor.iloc[0]["状态"], "🟢 已完成")
        self.assertEqual(editor.iloc[0]["备注"], "已核对")
        records = editor_records(editor)
        self.assertEqual(records[0]["status"], "completed")
        self.assertEqual(records[0]["task_name"], "每日检查")

    def test_unsaved_date_inherits_latest_earlier_record_without_writing(self):
        client = MagicMock()
        query = client.table.return_value
        for method in ("select", "eq", "lt", "order", "limit"):
            getattr(query, method).return_value = query
        previous = {"id": "old-day", "work_date": "2026-09-13", "summary": "继续对接"}
        query.execute.side_effect = [
            MagicMock(data=[]), MagicMock(data=[previous]),
            MagicMock(data=[{"task_id": "daily", "status": "completed", "note": "已核对"}]),
        ]

        day, records = load_daily_work(client, "a", date(2026, 9, 14), inherit_previous=True)

        self.assertEqual(day, previous)
        query.lt.assert_called_once_with("work_date", "2026-09-14")
        query.order.assert_called_once_with("work_date", desc=True)
        query.eq.assert_any_call("owner_username", "a")
        editor = build_daily_editor(self.tasks, records)
        self.assertEqual(editor.iloc[0]["状态"], "🟢 已完成")
        self.assertEqual(editor.iloc[0]["备注"], "已核对")
        self.assertEqual(editor.iloc[1]["状态"], "⚪ 不适用")
        query.upsert.assert_not_called()
        query.insert.assert_not_called()

    def test_saved_target_date_takes_precedence_over_previous(self):
        client = MagicMock()
        query = client.table.return_value
        for method in ("select", "eq", "limit"):
            getattr(query, method).return_value = query
        current = {"id": "today", "work_date": "2026-09-14"}
        query.execute.side_effect = [MagicMock(data=[current]), MagicMock(data=[])]

        day, _ = load_daily_work(client, "a", date(2026, 9, 14), inherit_previous=True)

        self.assertEqual(day, current)
        query.lt.assert_not_called()

    def test_no_earlier_record_uses_normal_defaults(self):
        client = MagicMock()
        query = client.table.return_value
        for method in ("select", "eq", "lt", "order", "limit"):
            getattr(query, method).return_value = query
        query.execute.return_value = MagicMock(data=[])

        day, records = load_daily_work(client, "a", date(2026, 9, 14), inherit_previous=True)

        self.assertEqual(day, {})
        self.assertTrue(records.empty)
        self.assertEqual(client.table.call_count, 2)

    def test_exact_date_loader_does_not_implicitly_inherit(self):
        client = MagicMock()
        query = client.table.return_value
        for method in ("select", "eq", "limit"):
            getattr(query, method).return_value = query
        query.execute.return_value = MagicMock(data=[])

        day, _ = load_daily_work(client, "a", date(2026, 9, 14))

        self.assertEqual(day, {})
        query.lt.assert_not_called()

    def test_ui_date_switch_keeps_independent_drafts_and_saved_content(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_string('''
from datetime import date
from unittest.mock import patch
import pandas as pd
from ui.daily_work.records import render_daily_record

tasks = pd.DataFrame([{"id": "task", "section": "客户", "task_name": "订单确认", "task_kind": "daily"}])
def load(client, owner, selected, inherit_previous=False):
    assert inherit_previous
    if selected == date(2026, 9, 13):
        return {"id": "saved", "work_date": "2026-09-13", "summary": "旧日总结"}, pd.DataFrame([{"task_id": "task", "status": "completed", "note": "旧日备注"}])
    return {"id": "previous", "work_date": "2026-09-13", "summary": "旧日总结"}, pd.DataFrame([{"task_id": "task", "status": "completed", "note": "旧日备注"}])
with patch("ui.daily_work.records.load_tasks", return_value=tasks), patch("ui.daily_work.records.load_daily_work", side_effect=load):
    render_daily_record(None, "a", "Andy", date(2026, 9, 14))
''').run()
        self.assertFalse(app.exception)
        self.assertIn("2026-09-13", app.info[0].value)
        self.assertEqual(app.text_area[0].value, "旧日总结")
        app.text_area[0].set_value("今天的新总结").run()
        self.assertEqual(app.text_area[0].value, "今天的新总结")
        app.date_input[0].set_value(date(2026, 9, 13)).run()
        self.assertFalse(app.exception)
        self.assertFalse(any("已带入" in item.value for item in app.info))
        self.assertEqual(app.text_area[0].value, "旧日总结")
        app.date_input[0].set_value(date(2026, 9, 14)).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_area[0].value, "旧日总结")

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

    def test_history_status_cells_use_semantic_colors(self):
        detail = pd.DataFrame({
            "状态": ["🟢 已完成", "🟡 待处理", "⚪ 不适用"],
        })

        html = style_status_table(detail).to_html()

        self.assertIn("background-color: #dcfce7", html)
        self.assertIn("background-color: #fef3c7", html)
        self.assertIn("background-color: #f3f4f6", html)

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

    def test_every_daily_work_grid_expands_to_show_all_rows(self):
        records = (PROJECT_ROOT / "ui/daily_work/records.py").read_text()
        settings = (PROJECT_ROOT / "ui/daily_work/settings.py").read_text()

        self.assertEqual(records.count("height=fit_table_height("), 3)
        self.assertEqual(settings.count("height=fit_table_height("), 1)


if __name__ == "__main__":
    unittest.main()
