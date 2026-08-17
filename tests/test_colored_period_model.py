import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from automation.production import ProductionDataResult
from automation.sync.colored_period import (
    LOOKBACK_DAYS,
    _date_chunks,
    build_colored_platform_status,
    load_colored_api_period_model,
    refresh_colored_api_period,
)


class ColoredPeriodModelTests(unittest.TestCase):
    def test_default_model_window_is_thirty_complete_days(self):
        self.assertEqual(LOOKBACK_DAYS, 30)

    def test_platform_status_lists_read_and_missing_with_next_action(self):
        model = type("Model", (), {
            "included_platforms": ("Haloo",),
            "missing_platforms": ("SDS1",),
            "start_date": date(2026, 5, 18),
            "end_date": date(2026, 8, 15),
        })()

        status = build_colored_platform_status(model, ("Haloo", "SDS1"))

        self.assertEqual(status["平台"].tolist(), ["Haloo", "SDS1"])
        self.assertEqual(status["读取状态"].tolist(), ["已读取", "未开始"])
        self.assertEqual(status.iloc[0]["下一步"], "无需操作")
        self.assertIn("开始读取", status.iloc[1]["下一步"])

    def test_persistence_failure_does_not_erase_successful_api_read(self):
        rows = pd.DataFrame([
            _production_row("红色", "L", 40, "品牌A"),
        ])

        with tempfile.TemporaryDirectory() as directory, patch(
            "automation.production_cache.CACHE_DIR", Path(directory)
        ), patch(
            "automation.sync.colored_period.DTF_PRODUCTION_PLATFORMS",
            ("S2B",),
        ), patch(
            "automation.sync.colored_period.load_platform_credentials",
            return_value={"token": "test"},
        ), patch(
            "automation.sync.colored_period.load_production_data",
            return_value=ProductionDataResult(rows, "S2B API"),
        ), patch(
            "automation.sync.colored_period.replace_daily_platform_consumption",
            side_effect=RuntimeError(
                "PGRST202 replace_platform_daily_consumption missing"
            ),
        ):
            model = refresh_colored_api_period(
                date(2026, 8, 17), {}, days=1, chunk_days=1,
                max_workers=1, supabase=object(),
            )

        status = build_colored_platform_status(model, ("S2B",))
        self.assertEqual(status.iloc[0]["读取状态"], "已读取（待保存）")
        self.assertIn("生产消耗模型 SQL", status.iloc[0]["下一步"])
        self.assertFalse(model.data.empty)

    def test_ninety_days_are_split_into_bounded_date_chunks(self):
        chunks = _date_chunks(date(2026, 5, 18), date(2026, 8, 15), 7)

        self.assertEqual(len(chunks), 13)
        self.assertEqual(chunks[0], (date(2026, 5, 18), date(2026, 5, 24)))
        self.assertEqual(chunks[-1], (date(2026, 8, 10), date(2026, 8, 15)))

    def test_platform_and_date_chunks_merge_brands_by_color_and_size(self):
        rows = pd.DataFrame([
            _production_row("红色", "L", 40, "品牌A"),
            _production_row("红色", "L", 60, "品牌B"),
        ])
        calls = []

        def load(platform, start_date, end_date, credentials=None):
            calls.append((platform, start_date, end_date, credentials))
            return ProductionDataResult(rows.copy(), f"{platform} API")

        with tempfile.TemporaryDirectory() as directory, patch(
            "automation.production_cache.CACHE_DIR", Path(directory)
        ), patch(
            "automation.sync.colored_period.DTF_PRODUCTION_PLATFORMS",
            ("平台A", "平台B"),
        ), patch(
            "automation.sync.colored_period.load_platform_credentials",
            side_effect=lambda platform, _secrets: {"token": platform},
        ), patch(
            "automation.sync.colored_period.load_production_data",
            side_effect=load,
        ):
            model = refresh_colored_api_period(
                date(2026, 8, 17), {}, days=8, chunk_days=4,
                max_workers=4,
            )
            cached = load_colored_api_period_model(date(2026, 8, 17), 8)

        self.assertEqual(len(calls), 4)
        self.assertEqual(set(model.included_platforms), {"平台A", "平台B"})
        self.assertEqual(len(cached.data), 1)
        self.assertEqual(cached.data.iloc[0]["颜色"], "红色")
        self.assertEqual(cached.data.iloc[0]["尺码"], "L")
        self.assertEqual(cached.data.iloc[0]["平台生产日均"], 50)
        self.assertEqual(cached.source, "local_cache")

    def test_deployment_prefers_persisted_database_model(self):
        persisted = pd.DataFrame([{
            "business_date": "2026-08-16", "platform": "S2B",
            "color": "黄色", "size": "L", "quantity": 300,
            "record_count": 10,
        }])
        with patch(
            "automation.sync.colored_period.load_daily_platform_consumption",
            return_value=persisted,
        ), patch(
            "automation.sync.colored_period.load_platform_sync_coverage",
            return_value={"S2B": {date(2026, 8, 16)}},
        ), patch(
            "automation.sync.colored_period.load_production_cache"
        ) as local_cache:
            model = load_colored_api_period_model(
                date(2026, 8, 17), days=30, supabase=object()
            )

        self.assertEqual(model.source, "database")
        self.assertEqual(model.data.iloc[0]["平台生产日均"], 10)
        local_cache.assert_not_called()

    def test_coverage_audit_failure_does_not_hide_database_model(self):
        persisted = pd.DataFrame([{
            "business_date": "2026-08-16", "platform": "S2B",
            "color": "黄色", "size": "L", "quantity": 300,
            "record_count": 10,
        }])
        with patch(
            "automation.sync.colored_period.load_daily_platform_consumption",
            return_value=persisted,
        ), patch(
            "automation.sync.colored_period.load_platform_sync_coverage",
            side_effect=RuntimeError("coverage table unavailable"),
        ), patch(
            "automation.sync.colored_period.load_production_cache"
        ) as local_cache:
            model = load_colored_api_period_model(
                date(2026, 8, 17), days=30, supabase=object()
            )

        self.assertEqual(model.source, "database")
        self.assertFalse(model.data.empty)
        self.assertIn("coverage table", model.storage_error)
        local_cache.assert_not_called()


def _production_row(color, size, quantity, brand):
    return {
        "部门": "DTF", "品类": "彩色短袖", "颜色": color,
        "尺码": size, "数量": quantity, "品牌": brand,
        "生产项状态": "完成",
    }


if __name__ == "__main__":
    unittest.main()
