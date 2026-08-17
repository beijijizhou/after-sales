import unittest
from datetime import date
from unittest.mock import Mock

import pandas as pd

from db.production_consumption import (
    build_daily_platform_consumption,
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


def _row(brand, timestamp, quantity):
    return {
        "部门": "DTF", "品类": "彩色短袖", "品牌": brand,
        "颜色": "红色", "尺码": "L", "数量": quantity,
        "生产完成时间": timestamp,
    }


if __name__ == "__main__":
    unittest.main()
