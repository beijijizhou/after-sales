from datetime import date
import unittest
from unittest.mock import patch

import pandas as pd

from automation.sync.daily_inventory_consumption import (
    AUTOMATIC_DAILY_FLOWS,
    AutomaticDailyPreview,
    apply_automatic_daily_batch_previews,
    build_automatic_daily_batch_summary,
    load_automatic_daily_batch_previews,
    _load_flow_preview,
)
from db.inventory.dashboard import (
    DAILY_COMPLETION_START_DATE,
    build_automatic_missing_dates,
    build_daily_completion_dates,
    build_daily_completion_table,
    build_today_completion_status,
)


class InventoryDashboardTests(unittest.TestCase):
    def test_daily_completion_business_start_is_august_first(self):
        self.assertEqual(
            DAILY_COMPLETION_START_DATE, date(2026, 8, 1)
        )

    def test_daily_completion_separates_four_flows(self):
        movements = pd.DataFrame([
            {
                "department": "DTF", "category": "黑白短袖",
                "movement_date": "2026-08-03", "quantity_change": -100,
                "reason": "仓库每日出货", "batch_id": "bw",
                "reversal_of_batch_id": None,
            },
            {
                "department": "DTF", "category": "彩色短袖",
                "movement_date": "2026-08-04", "quantity_change": -50,
                "reason": "彩色短袖生产自动扣减 2026-08-04",
                "batch_id": "color", "reversal_of_batch_id": None,
            },
            {
                "department": "UV", "category": "铁板画",
                "movement_date": "2026-08-04", "quantity_change": -20,
                "reason": "Google Sheets UV每日消耗｜2026-08-04｜Tie_2030",
                "batch_id": "uv", "reversal_of_batch_id": None,
            },
        ])
        consumables = pd.DataFrame([{
            "id": "c1", "movement_type": "issue",
            "movement_date": "2026-08-02", "reversal_of_batch_id": None,
        }])

        result = build_daily_completion_dates(movements, consumables)

        self.assertEqual(result["black_white"], {date(2026, 8, 3)})
        self.assertEqual(result["colored"], {date(2026, 8, 4)})
        self.assertEqual(result["uv"], {date(2026, 8, 4)})
        self.assertEqual(result["consumables"], {date(2026, 8, 2)})

    def test_completion_table_lists_missing_dates_and_action(self):
        completed = {
            "black_white": {date(2026, 8, 3)},
            "consumables": {date(2026, 8, 4)},
            "colored": {date(2026, 8, 3), date(2026, 8, 4)},
            "uv": set(),
        }

        result = build_daily_completion_table(
            completed, date(2026, 8, 3), date(2026, 8, 4)
        ).set_index("出库项目")

        self.assertEqual(result.loc["黑白短袖", "待处理日期"], "08/04")
        self.assertEqual(result.loc["彩色短袖", "待处理天数"], 0)
        self.assertEqual(
            result.loc["UV 生产库存", "处理方式"], "读取来源并扣减"
        )

    def test_automatic_sources_are_registered_in_one_place(self):
        self.assertEqual(
            [flow.code for flow in AUTOMATIC_DAILY_FLOWS],
            ["colored", "uv"],
        )

    def test_automatic_date_options_only_include_missing_sources(self):
        completed = {
            "colored": {date(2026, 8, 3), date(2026, 8, 4)},
            "uv": {date(2026, 8, 4)},
        }

        result = build_automatic_missing_dates(
            completed, date(2026, 8, 3), date(2026, 8, 4)
        )

        self.assertEqual(
            result,
            {date(2026, 8, 3): "UV 生产库存"},
        )

    def test_today_is_in_progress_instead_of_missing(self):
        today = date(2026, 8, 6)
        completed = {
            "black_white": {today},
            "consumables": set(),
            "colored": set(),
            "uv": {today},
        }

        status = build_today_completion_status(completed, today)
        missing = build_automatic_missing_dates(
            completed, date(2026, 8, 1), date(2026, 8, 5)
        )

        self.assertEqual(status["completed"], ["黑白短袖", "UV 生产库存"])
        self.assertEqual(status["pending"], ["DTF 耗材", "彩色短袖"])
        self.assertNotIn(today, missing)

    def test_batch_preview_summary_keeps_date_and_source(self):
        colored, uv = AUTOMATIC_DAILY_FLOWS
        previews = {
            date(2026, 8, 2): {
                "colored": AutomaticDailyPreview(
                    colored, "ready", 120, pd.DataFrame()
                ),
            },
            date(2026, 8, 3): {
                "uv": AutomaticDailyPreview(
                    uv, "blocked", 80, pd.DataFrame(), "库存不足"
                ),
            },
        }

        result = build_automatic_daily_batch_summary(previews)

        self.assertEqual(result["日期"].tolist(), [
            date(2026, 8, 2), date(2026, 8, 3),
        ])
        self.assertEqual(result["项目"].tolist(), [
            "彩色短袖", "UV 生产库存",
        ])
        self.assertEqual(result["预计扣减"].tolist(), [120, 80])

    def test_batch_loader_only_keeps_sources_missing_on_each_date(self):
        from unittest.mock import patch

        colored, uv = AUTOMATIC_DAILY_FLOWS
        daily = {
            "colored": AutomaticDailyPreview(
                colored, "ready", 120, pd.DataFrame()
            ),
            "uv": AutomaticDailyPreview(
                uv, "ready", 80, pd.DataFrame()
            ),
        }
        missing = {
            date(2026, 8, 2): "彩色短袖",
            date(2026, 8, 3): "UV 生产库存",
        }
        with patch(
            "automation.sync.daily_inventory_consumption."
            "load_automatic_daily_previews",
            return_value=daily,
        ):
            result = load_automatic_daily_batch_previews(
                object(), missing, object(), "sheet"
            )

        self.assertEqual(set(result[date(2026, 8, 2)]), {"colored"})
        self.assertEqual(set(result[date(2026, 8, 3)]), {"uv"})

    def test_batch_apply_returns_results_by_date_and_source(self):
        from unittest.mock import patch

        previews = {
            date(2026, 8, 2): {},
            date(2026, 8, 3): {},
        }
        with patch(
            "automation.sync.daily_inventory_consumption."
            "apply_automatic_daily_previews",
            side_effect=[({"colored": 120}, {}), ({"uv": 80}, {})],
        ):
            results, errors = apply_automatic_daily_batch_previews(
                object(), previews, "Andy"
            )

        self.assertEqual(errors, {})
        self.assertEqual(results, {
            (date(2026, 8, 2), "colored"): 120,
            (date(2026, 8, 3), "uv"): 80,
        })

    def test_colored_preview_blocks_unreconciled_or_missing_sources(self):
        colored = AUTOMATIC_DAILY_FLOWS[0]
        rows = pd.DataFrame([
            {"状态": "可扣减", "预计扣减": 548},
            {"状态": "库存为 0（待清点）", "预计扣减": 0},
        ])
        sources = pd.DataFrame([
            {"平台": "汉森", "原始生产件数": 421},
            {"平台": "SDS1", "原始生产件数": 175},
            {"平台": "SDS2", "原始生产件数": 38},
            {"平台": "方果", "原始生产件数": 3},
        ])
        with (
            patch(
                "automation.sync.daily_inventory_consumption."
                "load_colored_day_deducted_total", return_value=0,
            ),
            patch(
                "automation.sync.daily_inventory_consumption."
                "build_colored_daily_preview", return_value=rows,
            ),
            patch(
                "automation.sync.daily_inventory_consumption."
                "build_colored_platform_audit",
                return_value=(sources, {"missing_platforms": ["S2B"]}),
            ),
        ):
            result = _load_flow_preview(
                colored, object(), date(2026, 8, 2), None, "sheet"
            )

        self.assertEqual(result.state, "blocked")
        self.assertEqual(result.quantity, 548)
        self.assertEqual(result.source_quantity, 637)
        self.assertEqual(result.unresolved_quantity, 89)
        self.assertIn("89 件", result.message)
        self.assertIn("S2B", result.message)


if __name__ == "__main__":
    unittest.main()
