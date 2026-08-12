from datetime import date
import unittest

import pandas as pd

from utils.daily_usage_model import (
    EFFECTIVE_DAYS_GLOBAL_SINCE_FIRST,
    EFFECTIVE_DAYS_GLOBAL_WINDOW,
    EFFECTIVE_DAYS_PER_KEY_ACTIVITY,
    build_daily_usage_summary,
)


class DailyUsageModelTests(unittest.TestCase):
    def test_per_key_activity_mode_counts_only_active_dates(self):
        rows = pd.DataFrame([
            {"sku": "A", "日期": "2026-08-10", "数量": 10},
            {"sku": "A", "日期": "2026-08-12", "数量": 20},
        ])

        result = build_daily_usage_summary(
            rows,
            ["sku"],
            "数量",
            date(2026, 8, 12),
            14,
            effective_day_mode=EFFECTIVE_DAYS_PER_KEY_ACTIVITY,
            usage_column="日耗",
            effective_days_column="有效天数",
            natural_usage_column="自然日均",
            total_usage_column="总量",
            window_days_column="窗口天数",
            round_digits=2,
        )

        self.assertEqual(result.iloc[0]["有效天数"], 2)
        self.assertEqual(result.iloc[0]["窗口天数"], 14)
        self.assertEqual(result.iloc[0]["日耗"], 15.0)
        self.assertAlmostEqual(result.iloc[0]["自然日均"], 30 / 14, places=2)

    def test_global_window_mode_reuses_shared_observation_days(self):
        rows = pd.DataFrame([
            {"颜色": "红", "尺码": "L", "日期": "2026-08-10", "数量": 12},
            {"颜色": "红", "尺码": "L", "日期": "2026-08-12", "数量": 18},
        ])

        result = build_daily_usage_summary(
            rows,
            ["颜色", "尺码"],
            "数量",
            date(2026, 8, 12),
            14,
            effective_day_mode=EFFECTIVE_DAYS_GLOBAL_WINDOW,
            observation_dates=[date(2026, 8, 10), date(2026, 8, 11), date(2026, 8, 12)],
            usage_column="日耗",
            effective_days_column="有效天数",
            natural_usage_column="自然日均",
            total_usage_column="总量",
            window_days_column="窗口天数",
            round_digits=3,
        )

        self.assertEqual(result.iloc[0]["有效天数"], 3)
        self.assertEqual(result.iloc[0]["日耗"], 10.0)

    def test_global_since_first_mode_counts_zero_days_after_first_usage(self):
        rows = pd.DataFrame([
            {"材质": "铁牌", "型号": "1040", "日期": "2026-08-11", "数量": 100},
            {"材质": "铁牌", "型号": "2030", "日期": "2026-08-12", "数量": 200},
        ])

        result = build_daily_usage_summary(
            rows,
            ["材质", "型号"],
            "数量",
            date(2026, 8, 12),
            14,
            effective_day_mode=EFFECTIVE_DAYS_GLOBAL_SINCE_FIRST,
            observation_dates=[date(2026, 8, 11), date(2026, 8, 12)],
            usage_column="日耗",
            effective_days_column="有效天数",
            natural_usage_column="自然日均",
            total_usage_column="总量",
            window_days_column="窗口天数",
            round_digits=1,
        )

        self.assertEqual(result["有效天数"].tolist(), [2, 1])
        self.assertEqual(result["日耗"].tolist(), [50.0, 200.0])


if __name__ == "__main__":
    unittest.main()
