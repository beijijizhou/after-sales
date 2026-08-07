import unittest

import pandas as pd

from utils.production.platform_summary import (
    build_person_platform_summary_from_rpc,
)


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


def rpc_row(platform, scan_count, multiple_count):
    return {
        "person": "Susan",
        "platform": platform,
        "scan_count": scan_count,
        "multiple_order_count": multiple_count,
        "first_scan_at": "2026-08-06T13:00:00+00:00",
        "last_scan_at": "2026-08-06T14:00:00+00:00",
    }


if __name__ == "__main__":
    unittest.main()
