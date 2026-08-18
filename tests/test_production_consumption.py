import unittest
from datetime import date
from unittest.mock import Mock

import pandas as pd

from db.production_consumption import (
    build_daily_platform_consumption,
    load_daily_platform_consumption,
    record_platform_sync_failure,
    replace_daily_platform_consumption,
)


class ProductionConsumptionTests(unittest.TestCase):
    def test_daily_rows_merge_transfer_brands_by_date_color_and_size(self):
        rows = pd.DataFrame([
            _row("品牌A", "2026-08-15 10:00", 40),
            _row("品牌B", "2026-08-15 12:00", 60),
            _row("品牌A", "2026-08-16 09:00", 25),
        ])

        daily = build_daily_platform_consumption(rows)

        self.assertEqual(len(daily), 2)
        first = daily[daily["business_date"] == date(2026, 8, 15)].iloc[0]
        self.assertEqual(first["quantity"], 100)
        self.assertEqual(first["record_count"], 2)
        self.assertNotIn("brand", daily.columns)

    def test_black_white_uses_the_same_daily_builder(self):
        row = _row("Haloo", "2026-08-15 10:00", 80)
        row["品类"] = "黑白短袖"
        row["颜色"] = "黑"

        daily = build_daily_platform_consumption(
            pd.DataFrame([row]), "DTF", "黑白短袖"
        )

        self.assertEqual(daily.iloc[0]["color"], "黑")
        self.assertEqual(daily.iloc[0]["quantity"], 80)

    def test_replace_uses_atomic_range_rpc_for_idempotency(self):
        supabase = Mock()
        supabase.rpc.return_value.execute.return_value.data = [{
            "saved_rows": 1, "saved_quantity": 100,
        }]
        rows = pd.DataFrame([_row("品牌A", "2026-08-15 10:00", 100)])

        replace_daily_platform_consumption(
            supabase, "DTF", "彩色短袖", "Haloo",
            date(2026, 8, 15), date(2026, 8, 15), rows,
            "Haloo API", "Andy",
        )

        name, payload = supabase.rpc.call_args.args
        self.assertEqual(name, "replace_platform_daily_consumption")
        self.assertEqual(payload["p_department"], "DTF")
        self.assertEqual(payload["p_category"], "彩色短袖")
        self.assertEqual(payload["p_platform"], "Haloo")
        self.assertEqual(payload["p_rows"][0]["quantity"], 100)
        self.assertEqual(payload["p_operator"], "Andy")

    def test_rows_without_business_date_are_not_marked_as_saved(self):
        row = _row("品牌A", "2026-08-15 10:00", 100)
        row.pop("生产完成时间")

        with self.assertRaisesRegex(ValueError, "缺少可用生产日期"):
            replace_daily_platform_consumption(
                Mock(), "DTF", "彩色短袖", "Haloo",
                date(2026, 8, 15), date(2026, 8, 15),
                pd.DataFrame([row]), "Haloo API", "Andy",
            )

    def test_daily_fact_loader_reads_every_supabase_page(self):
        rows = [
            {
                "business_date": "2026-08-15", "platform": "S2B",
                "color": "黄色", "size": "L", "quantity": 1,
                "record_count": 1,
            }
            for _ in range(1005)
        ]

        class Query:
            def select(self, *_args):
                return self

            def eq(self, *_args):
                return self

            def gte(self, *_args):
                return self

            def lte(self, *_args):
                return self

            def order(self, *_args):
                return self

            def range(self, first, last):
                self.page = rows[first:last + 1]
                return self

            def execute(self):
                return type("Response", (), {"data": self.page})()

        client = type("Client", (), {
            "table": lambda self, _name: Query(),
        })()
        result = load_daily_platform_consumption(
            client, "DTF", "彩色短袖",
            date(2026, 7, 18), date(2026, 8, 16),
        )

        self.assertEqual(len(result), 1005)

    def test_failed_sync_is_persisted_for_deployment_audit(self):
        supabase = Mock()
        supabase.table.return_value.insert.return_value.execute.return_value.data = [
            {"status": "failed"}
        ]

        record_platform_sync_failure(
            supabase, "DTF", "彩色短袖", "七创",
            date(2026, 7, 18), date(2026, 8, 16),
            "本地缓存发布", "缺少可用生产日期",
            row_count=9, total_quantity=9, operator="Andy",
        )

        payload = supabase.table.return_value.insert.call_args.args[0]
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["total_quantity"], 9)
        self.assertIn("缺少可用生产日期", payload["source"])


def _row(brand, timestamp, quantity):
    return {
        "部门": "DTF", "品类": "彩色短袖", "品牌": brand,
        "颜色": "红色", "尺码": "L", "数量": quantity,
        "生产完成时间": timestamp,
    }


if __name__ == "__main__":
    unittest.main()
