import unittest
from datetime import date

import pandas as pd

from ui.production.simple_summary import build_person_total_table
from utils.production.platform_summary import (
    build_person_platform_summary,
    build_person_platform_summary_from_rpc,
    summarize_by_user,
)
from utils.production.normalization import prepare_production_df
from utils.production.hourly import summarize_by_hour


class ProductionPlatformSummaryTests(unittest.TestCase):
    def test_summary_includes_overview_percentages(self):
        rows = pd.DataFrame([
            rpc_row("Haloo", 10, 2),
            rpc_row("汉森", 5, 1),
            rpc_row("SDS", 5, 1),
        ])

        result = build_person_platform_summary_from_rpc(rows)

        self.assertEqual(result.loc[0, "总生产数量"], 20)
        self.assertEqual(result.loc[0, "多件订单数量"], 4)
        self.assertEqual(result.loc[0, "多件占比"], 20.0)
        self.assertEqual(result.loc[0, "汉森数量"], 5)
        self.assertEqual(result.loc[0, "汉森占比"], 25.0)
        self.assertEqual(result.loc[0, "Haloo 占比"], 50.0)
        self.assertEqual(result.loc[0, "小平台数量"], 10)
        self.assertEqual(result.loc[0, "小平台占比"], 50.0)

    def test_uv_person_table_ignores_platform_columns(self):
        summary = build_person_platform_summary_from_rpc(pd.DataFrame([
            rpc_row("Haloo", 10, 2),
            rpc_row("汉森", 5, 1),
        ]))

        result = build_person_total_table(summary)

        self.assertEqual(result.columns.tolist(), [
            "人员", "总生产数量", "多件订单数量", "多件占比", "时产量",
        ])
        self.assertNotIn("Haloo 数量", result.columns)

    def test_detail_fallback_counts_actual_pieces(self):
        raw_rows = pd.DataFrame([
            detail_row("Haloo", 1),
            detail_row("汉森", 3),
            detail_row("SDS", None),
        ])
        prepared = prepare_production_df(raw_rows, "scanned_by")

        person_totals = summarize_by_user(prepared, "scanned_by")
        platform_totals = build_person_platform_summary(
            prepared, "scanned_by"
        )

        self.assertEqual(person_totals.loc[0, "scan_count"], 5)
        self.assertEqual(person_totals.loc[0, "multiple_order_count"], 1)
        self.assertEqual(platform_totals.loc[0, "总生产数量"], 5)
        self.assertEqual(platform_totals.loc[0, "汉森数量"], 3)

        hourly_totals = summarize_by_hour(prepared, date(2026, 8, 6))
        self.assertEqual(hourly_totals["scan_count"].sum(), 5)
        self.assertEqual(hourly_totals["haloo_count"].sum(), 1)


def rpc_row(platform, scan_count, multiple_count):
    return {
        "person": "Susan",
        "platform": platform,
        "scan_count": scan_count,
        "multiple_order_count": multiple_count,
        "first_scan_at": "2026-08-06T13:00:00+00:00",
        "last_scan_at": "2026-08-06T14:00:00+00:00",
    }


def detail_row(platform, multiple_count):
    return {
        "barcode": f"code-{platform}",
        "platform": platform,
        "scanned_by": "Susan",
        "scanned_at": "2026-08-06T13:00:00+00:00",
        "multiple_count": multiple_count,
    }


if __name__ == "__main__":
    unittest.main()
