import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from automation.production import ProductionDataResult
from automation.production_batch import ALL_CLOTHING_PLATFORMS
from automation.sync.colored_period import (
    LOOKBACK_DAYS,
    _date_chunks,
    _load_chunk,
    _platform_chunks,
    build_colored_platform_status,
    load_colored_api_period_model,
    persist_cached_colored_api_period,
    refresh_colored_api_period,
)
from ui.inventory.planning.colored_consumption import (
    _default_refresh_platforms,
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

    def test_platform_with_rows_but_missing_dates_is_not_unstarted(self):
        model = type("Model", (), {
            "included_platforms": (),
            "missing_platforms": ("七创",),
            "available_platforms": ("七创",),
            "coverage_days": {},
            "platform_errors": {
                "七创": "七创 返回了彩色短袖数据，但缺少可用生产日期"
            },
            "persistence_errors": {},
            "start_date": date(2026, 7, 18),
            "end_date": date(2026, 8, 16),
        })()

        status = build_colored_platform_status(model, ("七创",))

        self.assertEqual(status.iloc[0]["读取状态"], "已读取｜日期待核对")
        self.assertIn("生产日期", status.iloc[0]["下一步"])

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

    def test_diy19_platforms_use_one_calendar_day_per_chunk(self):
        start = date(2026, 8, 14)
        end = date(2026, 8, 16)
        weekly = _date_chunks(start, end, 7)

        diy = _platform_chunks("七创", start, end, weekly)
        ordinary = _platform_chunks("S2B", start, end, weekly)

        self.assertEqual(diy, [
            (date(2026, 8, 14), date(2026, 8, 14)),
            (date(2026, 8, 15), date(2026, 8, 15)),
            (date(2026, 8, 16), date(2026, 8, 16)),
        ])
        self.assertEqual(ordinary, weekly)

    def test_forced_diy19_daily_read_does_not_reuse_stale_cache(self):
        fresh = pd.DataFrame([
            _production_row("黄色", "L", 12, "品牌A")
        ])
        with patch(
            "automation.sync.colored_period.load_production_cache",
            return_value=type("Cached", (), {
                "data": pd.DataFrame(), "source": "旧空缓存",
            })(),
        ) as cache, patch(
            "automation.sync.colored_period.load_production_data",
            return_value=ProductionDataResult(fresh, "七创单日API"),
        ) as fetch, patch(
            "automation.sync.colored_period.save_production_cache",
        ):
            rows, source = _load_chunk(
                "七创", date(2026, 8, 15), date(2026, 8, 15),
                {"token": "test"}, force_refresh=True,
            )

        cache.assert_not_called()
        fetch.assert_called_once()
        self.assertEqual(len(rows), 1)
        self.assertEqual(source, "七创单日API")

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

    def test_selected_platform_refresh_keeps_other_platform_cache(self):
        platform_a = pd.DataFrame([{
            **_production_row("红色", "L", 40, "品牌A"),
            "运营商": "平台A",
        }])
        platform_b = pd.DataFrame([{
            **_production_row("黄色", "M", 60, "品牌B"),
            "运营商": "平台B",
        }])
        calls = []

        def load(platform, start_date, end_date, credentials=None):
            calls.append(platform)
            return ProductionDataResult(platform_b.copy(), f"{platform} API")

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
            from automation.production_cache import save_production_cache
            save_production_cache(
                ALL_CLOTHING_PLATFORMS,
                date(2026, 8, 16), date(2026, 8, 16),
                platform_a, "已有平台A",
                extra_metadata={
                    "included_platforms": ["平台A"],
                    "platform_coverage_days": {"平台A": 1},
                },
            )
            model = refresh_colored_api_period(
                date(2026, 8, 17), {}, days=1, chunk_days=1,
                max_workers=1, platforms=("平台B",),
            )

        self.assertEqual(calls, ["平台B"])
        self.assertEqual(set(model.included_platforms), {"平台A", "平台B"})
        self.assertEqual(set(model.data["颜色"]), {"红色", "黄色"})

    def test_refresh_defaults_to_incomplete_platforms_only(self):
        status = pd.DataFrame([
            {"平台": "Haloo", "读取状态": "未开始"},
            {"平台": "莆田", "读取状态": "读取失败"},
            {"平台": "S2B", "读取状态": "已读取"},
        ])
        with patch(
            "ui.inventory.planning.colored_consumption."
            "DTF_PRODUCTION_PLATFORMS",
            ("Haloo", "莆田", "S2B"),
        ):
            selected = _default_refresh_platforms(status)

        self.assertEqual(selected, ["Haloo", "莆田"])

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

    def test_existing_local_cache_can_be_published_without_erp_request(self):
        cached = type("Cached", (), {
            "data": pd.DataFrame([
                {
                    **_production_row("黄色", "L", 40, "品牌A"),
                    "运营商": "S2B",
                },
                {
                    **_production_row("红色", "M", 60, "品牌B"),
                    "运营商": "SDS1",
                },
                {
                    "运营商": "S2B", "部门": "DTF",
                    "品类": "黑白短袖", "颜色": "白", "尺码": "L",
                    "数量": 999,
                },
            ]),
            "source": "现有本地缓存",
        })()
        with patch(
            "automation.sync.colored_period.load_production_cache",
            return_value=cached,
        ), patch(
            "automation.sync.colored_period.replace_daily_platform_consumption"
        ) as persist, patch(
            "automation.sync.colored_period.load_production_data"
        ) as erp:
            result = persist_cached_colored_api_period(
                date(2026, 8, 17), object(), operator="Andy"
            )

        self.assertEqual(result.platforms, ("S2B", "SDS1"))
        self.assertEqual(result.source_rows, 2)
        self.assertEqual(result.saved_platforms, ("S2B", "SDS1"))
        self.assertEqual(persist.call_count, 2)
        self.assertTrue(all(
            call.args[2] == "彩色短袖" for call in persist.call_args_list
        ))
        erp.assert_not_called()

    def test_cache_publish_preserves_successes_when_one_platform_fails(self):
        cached = type("Cached", (), {
            "data": pd.DataFrame([
                {
                    **_production_row("黄色", "L", 40, "品牌A"),
                    "运营商": "S2B",
                },
                {
                    **_production_row("红色", "M", 60, "品牌B"),
                    "运营商": "SDS1",
                },
            ]),
            "source": "现有本地缓存",
        })()

        def persist(_db, _department, _category, platform, *_args):
            if platform == "SDS1":
                raise RuntimeError("database unavailable")

        with patch(
            "automation.sync.colored_period.load_production_cache",
            return_value=cached,
        ), patch(
            "automation.sync.colored_period.replace_daily_platform_consumption",
            side_effect=persist,
        ):
            result = persist_cached_colored_api_period(
                date(2026, 8, 17), object()
            )

        self.assertEqual(result.saved_platforms, ("S2B",))
        self.assertIn("SDS1", result.errors)


def _production_row(color, size, quantity, brand):
    return {
        "部门": "DTF", "品类": "彩色短袖", "颜色": color,
        "尺码": size, "数量": quantity, "品牌": brand,
        "生产项状态": "完成",
    }


if __name__ == "__main__":
    unittest.main()
