from datetime import date
import unittest

import pandas as pd

from db.inventory.operations.outbound_audit import (
    audit_outbound_batch,
    find_missing_outbound_dates,
    find_outbound_inventory_issues,
    is_confirmed_outbound_row,
    verify_outbound_batch,
)
from ui.inventory.history.history_tables import (
    _format_signed_quantity,
    build_movement_detail_table,
)
from ui.inventory.history.history_batches import build_movement_batch_rows
from ui.inventory.history.history_filters import (
    filter_batches_by_outbound_kind,
    filter_history_batches,
    filter_reversal_scope,
)
from ui.inventory.page_tabs import inventory_tab_keys


class BatchQueryStub:
    def __init__(self, rows):
        self.data = rows

    def table(self, _name):
        return self

    def select(self, _columns):
        return self

    def eq(self, _column, _value):
        return self

    def execute(self):
        return self


class OutboundStatusTests(unittest.TestCase):
    def test_signed_quantity_format_does_not_mark_zero(self):
        self.assertEqual(_format_signed_quantity(500), "+500")
        self.assertEqual(_format_signed_quantity(-500), "-500")
        self.assertEqual(_format_signed_quantity(0), "0")

    def test_manual_and_system_inventory_operations_have_distinct_tabs(self):
        self.assertIn(
            "仓库每日出库",
            inventory_tab_keys("DTF", category=""),
        )
        self.assertIn(
            "系统库存扣减",
            inventory_tab_keys("DTF", category=""),
        )
        self.assertIn(
            "仓库每日出库",
            inventory_tab_keys("DTF", category="黑白短袖"),
        )
        self.assertNotIn(
            "系统库存扣减",
            inventory_tab_keys("DTF", category="黑白短袖"),
        )
        self.assertIn(
            "系统库存扣减",
            inventory_tab_keys("DTF", category="彩色短袖"),
        )
        self.assertIn(
            "系统库存扣减", inventory_tab_keys("UV", category="铁板画")
        )
        self.assertNotIn(
            "仓库每日出库", inventory_tab_keys("DTF", category="卫衣")
        )
        self.assertNotIn(
            "系统库存扣减", inventory_tab_keys("DTF", category="卫衣")
        )

    def test_sku_workflows_are_not_embedded_in_production_inventory(self):
        tabs = inventory_tab_keys("DTF", category="黑白短袖")

        self.assertNotIn("SKU 管理", tabs)
        self.assertNotIn("SKU 操作历史", tabs)

    def test_combined_ledger_contains_daily_and_temporary_batches(self):
        batches = pd.DataFrame([
            {
                "记录类别": "库存表格记录",
                "类型": "出库",
                "备注": "仓库每日出货",
            },
            {
                "记录类别": "库存表格记录",
                "类型": "出库",
                "备注": "临时库存调整｜库存明细直接编辑",
            },
            {
                "记录类别": "撤销记录",
                "类型": "撤销出库",
                "备注": "撤销：仓库每日出货",
            },
        ])

        result = filter_history_batches(batches, "all")

        self.assertEqual(len(result), 2)
        self.assertEqual(
            set(result["备注"]),
            {
                "仓库每日出货",
                "临时库存调整｜库存明细直接编辑",
            },
        )

    def test_filters_three_outbound_history_kinds(self):
        batches = pd.DataFrame([
            {"类型": "出库", "备注": "每日正常出货", "数量": 100},
            {"类型": "出库", "备注": "仓库每日出货", "数量": 200},
            {
                "类型": "出库",
                "备注": "临时库存调整｜库存明细直接编辑",
                "数量": 300,
            },
            {"类型": "入库", "备注": "临时库存调整", "数量": 400},
            {"类型": "入库", "备注": "货柜入库：9柜", "数量": 500},
        ])

        self.assertEqual(
            filter_batches_by_outbound_kind(
                batches, "每日库存扣减"
            )["数量"].tolist(),
            [100, 200],
        )
        self.assertEqual(
            filter_batches_by_outbound_kind(
                batches, "每日出库"
            )["数量"].tolist(),
            [100, 200],
        )
        self.assertEqual(
            filter_batches_by_outbound_kind(
                batches, "临时库存调整"
            )["数量"].tolist(),
            [300, 400],
        )
        self.assertEqual(
            filter_batches_by_outbound_kind(
                batches, "货柜入库"
            )["数量"].tolist(),
            [500],
        )

    def test_system_deductions_share_daily_consumption_filter(self):
        batches = pd.DataFrame([
            {
                "类型": "出库",
                "备注": "彩色短袖生产自动扣减 2026-08-03",
                "数量": 120,
            },
            {
                "类型": "出库",
                "备注": "Google Sheets UV每日消耗｜2026-08-03｜Tie_2030",
                "数量": 240,
            },
            {
                "类型": "出库",
                "备注": "临时库存调整",
                "数量": 30,
            },
        ])

        daily = filter_batches_by_outbound_kind(
            batches, "每日库存扣减"
        )
        temporary_adjustment = filter_batches_by_outbound_kind(
            batches, "临时库存调整"
        )

        self.assertEqual(daily["数量"].tolist(), [120, 240])
        self.assertEqual(temporary_adjustment["数量"].tolist(), [30])

    def test_reversal_scope_separates_all_outbound_workflows(self):
        batches = pd.DataFrame([
            {"类型": "出库", "备注": "仓库每日出货", "数量": 100},
            {
                "类型": "出库",
                "备注": "彩色短袖生产自动扣减 2026-08-05",
                "数量": 200,
            },
            {
                "类型": "出库",
                "备注": "Google Sheets UV每日消耗｜2026-08-05",
                "数量": 300,
            },
            {
                "类型": "出库",
                "备注": "临时库存调整｜补录",
                "数量": 400,
            },
            {"类型": "入库", "备注": "货柜入库：11柜", "数量": 500},
        ])

        self.assertEqual(
            filter_reversal_scope(
                batches, "仓库每日出库"
            )["数量"].tolist(),
            [100],
        )
        self.assertEqual(
            filter_reversal_scope(
                batches, "系统库存扣减"
            )["数量"].tolist(),
            [200, 300],
        )
        self.assertEqual(
            filter_reversal_scope(
                batches, "临时库存调整"
            )["数量"].tolist(),
            [400],
        )
        self.assertEqual(
            filter_reversal_scope(
                batches, "其他出入库"
            )["数量"].tolist(),
            [500],
        )

    def test_recognizes_daily_outbound_reasons_on_current_dates(self):
        current_date = date(2026, 7, 29)

        self.assertTrue(
            is_confirmed_outbound_row(current_date, "每日正常出货")
        )
        self.assertFalse(
            is_confirmed_outbound_row(
                current_date, "临时库存调整｜库存明细直接编辑"
            )
        )
        self.assertTrue(
            is_confirmed_outbound_row(current_date, "仓库每日出货")
        )
        self.assertTrue(
            is_confirmed_outbound_row(date(2026, 7, 28), "每日正常出货")
        )

    def test_lists_every_missing_calendar_date(self):
        recorded = {
            date(2026, 7, 24),
            date(2026, 7, 26),
            date(2026, 7, 28),
        }

        result = find_missing_outbound_dates(
            recorded,
            date(2026, 7, 24),
            date(2026, 7, 29),
        )

        self.assertEqual(
            result,
            [
                date(2026, 7, 25),
                date(2026, 7, 27),
                date(2026, 7, 29),
            ],
        )

    def test_verifies_saved_row_count_and_total(self):
        query = BatchQueryStub([
            {"quantity_change": -144},
            {"quantity_change": -1500},
        ])

        self.assertEqual(
            verify_outbound_batch(query, "batch-id"),
            (2, 1644, True),
        )

    def test_detects_size_level_mismatch(self):
        query = BatchQueryStub([{
            "movement_date": "2026-07-28",
            "brand": "Haloo",
            "material": "CVC",
            "color": "黑",
            "size": "M",
            "quantity_change": -900,
        }])
        expected = pd.DataFrame([{
            "日期": date(2026, 7, 28),
            "操作": "扣减",
            "品牌": "Haloo",
            "材质": "CVC",
            "颜色": "黑",
            "尺码": "S",
            "数量": 900,
        }])

        self.assertEqual(
            verify_outbound_batch(query, "batch-id", expected),
            (1, 900, False),
        )

    def test_audit_shows_total_and_sku_level_difference(self):
        query = BatchQueryStub([{
            "movement_date": "2026-07-28",
            "brand": "Haloo",
            "material": "CVC",
            "color": "黑",
            "size": "M",
            "quantity_change": -900,
        }])
        expected = pd.DataFrame([{
            "日期": date(2026, 7, 28),
            "操作": "扣减",
            "品牌": "Haloo",
            "材质": "CVC",
            "颜色": "黑",
            "尺码": "S",
            "数量": 900,
        }])

        audit, mismatches = audit_outbound_batch(
            query, "batch-id", expected
        )

        self.assertEqual(audit["expected_total"], 900)
        self.assertEqual(audit["saved_total"], 900)
        self.assertEqual(audit["difference"], 0)
        self.assertFalse(audit["rows_match"])
        self.assertFalse(audit["passed"])
        self.assertEqual(len(mismatches), 2)
        self.assertEqual(set(mismatches["尺码"]), {"S", "M"})

    def test_outbound_history_uses_signed_display_quantities(self):
        movements = pd.DataFrame([{
            "movement_date": "2026-07-28",
            "created_at": "2026-07-28T20:00:00+00:00",
            "department": "DTF",
            "category": "黑白短袖",
            "brand": "Haloo",
            "material": "CVC",
            "color": "黑",
            "size": "S",
            "quantity_change": -900,
            "reason": "每日正常出货",
            "created_by": "w",
            "source_type": None,
        }])

        result = build_movement_detail_table(
            movements, ["S", "M", "L"]
        )

        self.assertEqual(result.iloc[0]["流水记录类型"], "🔴 出库")
        self.assertEqual(int(result.iloc[0]["S"]), -900)
        self.assertEqual(int(result.iloc[0]["M"]), 0)
        self.assertEqual(int(result.iloc[0]["合计"]), -900)
        self.assertEqual(result.iloc[0]["消耗来源"], "人工登记")

    def test_system_outbound_history_shows_automatic_source(self):
        movements = pd.DataFrame([{
            "movement_date": "2026-08-03",
            "created_at": "2026-08-03T20:00:00+00:00",
            "department": "UV", "category": "铁板画",
            "brand": "", "material": "铁牌", "color": "白",
            "size": "2030", "quantity_change": -2000,
            "reason": "Google Sheets UV每日消耗｜2026-08-03｜Tie_2030",
            "created_by": "system", "source_type": None,
        }])

        result = build_movement_detail_table(movements, ["2030"])

        self.assertEqual(result.iloc[0]["消耗来源"], "系统读取")

    def test_uv_daily_sheet_is_one_ledger_batch_across_skus(self):
        movements = pd.DataFrame([
            {
                "movement_date": "2026-08-03",
                "created_at": "2026-08-03T20:00:00+00:00",
                "department": "UV", "category": "铁板画",
                "brand": "", "material": "铁牌", "color": "白",
                "size": "2030", "quantity_change": -2000,
                "reason": "Google Sheets UV每日消耗｜2026-08-03｜Tie_2030",
                "created_by": "system", "batch_id": "old-batch-1",
                "reversal_of_batch_id": None,
            },
            {
                "movement_date": "2026-08-03",
                "created_at": "2026-08-03T20:01:00+00:00",
                "department": "UV", "category": "木板画",
                "brand": "", "material": "木板", "color": "白",
                "size": "2030", "quantity_change": -300,
                "reason": "Google Sheets UV每日消耗｜2026-08-03｜Muban_2030",
                "created_by": "system", "batch_id": "old-batch-2",
                "reversal_of_batch_id": None,
            },
        ])

        result = build_movement_batch_rows(movements)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["数量"], 2300)
        self.assertEqual(result[0]["品类"], "多品类")
        self.assertIn("2 个 SKU", result[0]["备注"])

    def test_precheck_reports_missing_and_insufficient_skus(self):
        expected = pd.DataFrame([
            {
                "品牌": "B64", "材质": "160g", "颜色": "白",
                "尺码": "L", "数量": 2736,
            },
            {
                "品牌": "Haloo", "材质": "CVC", "颜色": "白",
                "尺码": "M", "数量": 936,
            },
        ])
        inventory = pd.DataFrame([{
            "brand": "Haloo", "material": "CVC", "color": "白",
            "size": "M", "quantity": 0,
        }])

        result = find_outbound_inventory_issues(
            expected, inventory
        )

        self.assertEqual(len(result), 2)
        issues = dict(zip(result["品牌"], result["问题"]))
        self.assertEqual(issues["B64"], "SKU 不存在")
        self.assertEqual(issues["Haloo"], "库存不足")


if __name__ == "__main__":
    unittest.main()
