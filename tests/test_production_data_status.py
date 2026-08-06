import unittest

import pandas as pd

from ui.production_data.status import build_platform_read_status


class ProductionDataStatusTests(unittest.TestCase):
    def test_partial_cache_lists_missing_platform_and_saved_reason(self):
        source = {
            "data": pd.DataFrame({"运营商": ["SDS1", "S2B"]}),
            "metadata": {
                "included_platforms": ["SDS1", "S2B"],
                "missing_platforms": ["Haloo"],
                "platform_errors": {"Haloo": "登录已失效"},
            },
        }

        result = build_platform_read_status(
            source, ["Haloo", "S2B", "SDS1"]
        )
        indexed = {row["平台"]: row for row in result}

        self.assertEqual(indexed["Haloo"]["读取状态"], "未读取")
        self.assertEqual(indexed["Haloo"]["说明"], "登录已失效")
        self.assertEqual(indexed["S2B"]["读取状态"], "已读取")

    def test_old_cache_explains_that_failure_reason_was_not_saved(self):
        source = {
            "data": pd.DataFrame({"运营商": ["SDS1"]}),
            "metadata": {
                "included_platforms": ["SDS1"],
                "missing_platforms": ["S2B"],
            },
        }

        result = build_platform_read_status(source, ["SDS1", "S2B"])
        missing = next(row for row in result if row["平台"] == "S2B")

        self.assertIn("历史缓存未记录失败原因", missing["说明"])


if __name__ == "__main__":
    unittest.main()
