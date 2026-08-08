from datetime import date
import unittest
from unittest.mock import patch

import pandas as pd

from automation.sync.daily_inventory_consumption import (
    AUTOMATIC_DAILY_FLOWS,
    AutomaticDailyPreview,
    COLORED_FAST_PLATFORM_SCOPE,
    apply_automatic_daily_batch_previews,
    build_automatic_daily_batch_summary,
    load_automatic_daily_batch_previews,
    _load_flow_preview,
)
from automation.sync.dtf_colored_inventory import (
    apply_colored_daily_deduction,
    colored_partial_reason,
)
from db.inventory.dashboard import (
    DAILY_COMPLETION_START_DATE,
    build_automatic_missing_dates,
    build_daily_completion_dates,
    build_daily_operation_table,
    build_daily_completion_table,
    build_today_completion_status,
    build_today_completion_table,
)
from ui.inventory.dashboard import (
    _filter_automatic_missing_dates,
    _format_applied_result,
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

    def test_table_action_filters_automatic_preview_to_selected_flow(self):
        missing = {
            date(2026, 8, 2): "彩色短袖、UV 生产库存",
            date(2026, 8, 3): "彩色短袖",
            date(2026, 8, 4): "UV 生产库存",
        }
        self.assertEqual(
            _filter_automatic_missing_dates(missing, "彩色短袖"),
            {
                date(2026, 8, 2): "彩色短袖",
                date(2026, 8, 3): "彩色短袖",
            },
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

    def test_today_completion_table_is_actionable_without_marking_missing(self):
        today = date(2026, 8, 6)
        completed = {
            "black_white": set(),
            "consumables": {today},
            "colored": set(),
            "uv": set(),
        }

        result = build_today_completion_table(
            completed, today
        ).set_index("出库项目")

        self.assertEqual(result.loc["DTF 耗材", "今日状态"], "已完成")
        self.assertEqual(result.loc["黑白短袖", "今日状态"], "进行中")
        self.assertEqual(result["计入补录"].unique().tolist(), ["否"])
        self.assertEqual(
            result.loc["彩色短袖", "下一步"],
            "今日结束后由系统读取",
        )

    def test_daily_operation_table_combines_history_and_today(self):
        today = date(2026, 8, 6)
        completed = {
            "black_white": {date(2026, 8, 5)},
            "consumables": {today},
            "colored": set(),
            "uv": set(),
        }
        summary = build_daily_completion_table(
            completed, date(2026, 8, 5), date(2026, 8, 5)
        )

        result = build_daily_operation_table(
            summary, completed, today
        ).set_index("出库项目")

        self.assertEqual(result.loc["黑白短袖", "截止昨日"], "1/1 天")
        self.assertEqual(result.loc["DTF 耗材", "今日状态"], "已完成")
        self.assertEqual(result.loc["彩色短袖", "待补日期"], "08/05")
        self.assertEqual(
            result.loc["彩色短袖", "当前操作"],
            "系统预览并补扣 1 天",
        )

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
        self.assertEqual(
            result["数据范围"].tolist(),
            [
                f"快速补录：{COLORED_FAST_PLATFORM_SCOPE}",
                "Google Sheets",
            ],
        )

    def test_uv_preview_marks_iphone_outside_statistics_and_deduction(self):
        uv = AUTOMATIC_DAILY_FLOWS[1]
        preview_rows = pd.DataFrame([
            {
                "表格产品": "Tie_2030", "当日消耗": 2000,
                "预计扣减": 2000, "状态": "可扣减",
            },
            {
                "表格产品": "Iphone", "当日消耗": 500,
                "预计扣减": 0, "状态": "待分配 SKU（本次不扣）",
            },
        ])
        with (
            patch(
                "automation.sync.daily_inventory_consumption."
                "load_uv_daily_consumption_total", return_value=0,
            ),
            patch(
                "automation.sync.daily_inventory_consumption.load_daily_summary",
                return_value={"Tie_2030": 2000, "Iphone": 500},
            ),
            patch(
                "automation.sync.daily_inventory_consumption.load_inventory_items",
                return_value=pd.DataFrame(),
            ),
            patch(
                "automation.sync.daily_inventory_consumption.build_daily_sync_preview",
                return_value=preview_rows,
            ),
        ):
            result = _load_flow_preview(
                uv, object(), date(2026, 8, 7), object(), "sheet"
            )

        self.assertEqual(result.state, "ready")
        self.assertEqual(result.quantity, 2000)
        self.assertIn("Iphone（手机壳） 500 件", result.message)
        self.assertIn("未进入统计及库存扣减", result.message)

    def test_applied_result_reports_refreshed_completion_state(self):
        movement_date = date(2026, 8, 3)

        completed = _format_applied_result(
            movement_date, "colored", "彩色短袖", 548,
            {"colored": {movement_date}},
        )
        pending = _format_applied_result(
            movement_date, "colored", "彩色短袖", 500,
            {"colored": set()},
        )

        self.assertIn("已完成", completed)
        self.assertIn("仍有待处理数据", pending)

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

    def test_colored_only_batch_does_not_load_uv(self):
        colored, _uv = AUTOMATIC_DAILY_FLOWS
        with patch(
            "automation.sync.daily_inventory_consumption._load_flow_preview",
            return_value=AutomaticDailyPreview(
                colored, "ready", 120, pd.DataFrame()
            ),
        ) as load_preview:
            result = load_automatic_daily_batch_previews(
                object(), {date(2026, 8, 3): "彩色短袖"},
                None, "",
            )

        self.assertEqual(set(result[date(2026, 8, 3)]), {"colored"})
        self.assertEqual(
            [call.args[0].code for call in load_preview.call_args_list],
            ["colored"],
        )

    def test_batch_loader_ensures_colored_cache_one_day_at_a_time(self):
        colored, uv = AUTOMATIC_DAILY_FLOWS
        requested_dates = []
        progress = []

        def ensure_day(movement_date):
            requested_dates.append(movement_date)

        daily = {
            "colored": AutomaticDailyPreview(
                colored, "ready", 120, pd.DataFrame()
            ),
            "uv": AutomaticDailyPreview(
                uv, "ready", 80, pd.DataFrame()
            ),
        }
        missing = {
            date(2026, 8, 2): "彩色短袖、UV 生产库存",
            date(2026, 8, 3): "彩色短袖",
            date(2026, 8, 4): "UV 生产库存",
        }
        with patch(
            "automation.sync.daily_inventory_consumption."
            "load_automatic_daily_previews",
            return_value=daily,
        ):
            load_automatic_daily_batch_previews(
                object(), missing, object(), "sheet",
                ensure_colored_source=ensure_day,
                max_day_workers=2,
                report_day_progress=lambda day, project, state: (
                    progress.append((day, project, state))
                ),
            )

        self.assertEqual(
            set(requested_dates),
            {date(2026, 8, 2), date(2026, 8, 3)},
        )
        final_states = {
            day: state for day, _project, state in progress
        }
        self.assertEqual(final_states[date(2026, 8, 2)], "预览完成")
        self.assertEqual(final_states[date(2026, 8, 3)], "预览完成")
        self.assertEqual(final_states[date(2026, 8, 4)], "预览完成")

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

    def test_colored_preview_allows_valid_partial_deduction(self):
        colored = AUTOMATIC_DAILY_FLOWS[0]
        rows = pd.DataFrame([
            {"状态": "可扣减", "预计扣减": 719},
            {
                "状态": "库存为 0（待清点）",
                "预计扣减": 0,
                "未扣数量": 42,
            },
        ])
        sources = pd.DataFrame([
            {"平台": "S2B", "原始生产件数": 761},
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
                return_value=(sources, {"missing_platforms": []}),
            ),
        ):
            result = _load_flow_preview(
                colored, object(), date(2026, 8, 6), None, "sheet"
            )

        self.assertEqual(result.state, "ready")
        self.assertEqual(result.quantity, 719)
        self.assertEqual(result.unresolved_quantity, 42)
        self.assertIn("剩余 42 件", result.message)

    def test_colored_primary_platforms_allow_fast_preview(self):
        colored = AUTOMATIC_DAILY_FLOWS[0]
        rows = pd.DataFrame([{"状态": "可扣减", "预计扣减": 100}])
        sources = pd.DataFrame([
            {"平台": "汉森", "原始生产件数": 50},
            {"平台": "S2B", "原始生产件数": 50},
        ])
        metadata = {
            "included_platforms": ["汉森", "S2B", "SDS1", "SDS2"],
            "missing_platforms": ["Haloo", "隆丰"],
            "is_complete": False,
        }
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
                return_value=(sources, metadata),
            ),
        ):
            result = _load_flow_preview(
                colored, object(), date(2026, 8, 3), None, ""
            )

        self.assertEqual(result.state, "ready")
        self.assertIn("其余平台留待全平台核对", result.message)

    def test_partial_colored_deduction_keeps_reconciliation_reason(self):
        preview = pd.DataFrame([
            {
                "状态": "可扣减", "品牌": "Caribbean", "材质": "180g",
                "颜色": "蓝色", "尺码": "L", "预计扣减": 10,
                "未扣数量": 0,
            },
            {
                "状态": "库存为 0（待清点）", "品牌": "", "材质": "",
                "颜色": "粉色", "尺码": "S", "预计扣减": 0,
                "未扣数量": 2,
            },
        ])
        movement_date = date(2026, 8, 6)
        with (
            patch(
                "automation.sync.dtf_colored_inventory.apply_adjustment_rows"
            ) as apply_rows,
            patch(
                "automation.sync.dtf_colored_inventory."
                "load_daily_colored_production_source",
                return_value=(pd.DataFrame(), {
                    "included_platforms": ["汉森", "S2B", "SDS1", "SDS2"]
                }),
            ),
        ):
            quantity = apply_colored_daily_deduction(
                object(), preview, movement_date, "Andy"
            )

        self.assertEqual(quantity, 10)
        adjustment = apply_rows.call_args.args[3]
        reason = adjustment.iloc[0]["备注"]
        self.assertTrue(reason.startswith(colored_partial_reason(movement_date)))
        self.assertIn("来源 汉森、S2B、SDS1、SDS2", reason)
        self.assertIn("映射规则 colored-v1", reason)

    def test_partial_colored_reason_marks_daily_run_complete(self):
        movements = pd.DataFrame([{
            "department": "DTF", "category": "彩色短袖",
            "movement_date": "2026-08-06", "quantity_change": -719,
            "reason": "彩色短袖生产自动扣减 2026-08-06｜部分扣减",
            "batch_id": "partial", "reversal_of_batch_id": None,
        }])
        result = build_daily_completion_dates(
            movements, pd.DataFrame()
        )
        self.assertEqual(result["colored"], {date(2026, 8, 6)})


if __name__ == "__main__":
    unittest.main()
