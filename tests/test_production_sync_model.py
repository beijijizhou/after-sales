from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from automation.production import DTF_PRODUCTION_PLATFORMS, ProductionDataResult
from automation.production_batch import (
    ALL_CLOTHING_PLATFORMS,
    BatchProductionResult,
)
from automation.production_cache import save_production_cache
from automation.production_period import (
    load_period_production_model,
    load_recent_production_model,
)
from automation.sync.daily import sync_production_day


class ProductionSyncModelTests(unittest.TestCase):
    def test_cache_miss_fetches_one_day_and_keeps_consumption_model(self):
        target = date(2026, 8, 6)
        production = pd.DataFrame([
            {
                "生产项编码": "item-colored",
                "生产单号": "order-colored",
                "部门": "DTF",
                "品类": "彩色短袖",
                "材质": "180g",
                "颜色": "红色",
                "尺码": "L",
                "型号": "",
                "数量": 10,
                "生产项状态": "已完成",
                "运营商": "S2B",
                "创建时间": "2026-08-06 10:00:00",
                "生产完成时间": "2026-08-06 10:00:00",
            },
            {
                "生产项编码": "item-black-white",
                "生产单号": "order-black-white",
                "部门": "DTF",
                "品类": "黑白短袖",
                "材质": "160g",
                "颜色": "黑",
                "尺码": "XL",
                "型号": "",
                "数量": 100,
                "生产项状态": "已完成",
                "运营商": "S2B",
                "创建时间": "2026-08-06 10:00:00",
                "生产完成时间": "2026-08-06 10:00:00",
            },
        ])
        empty = production.iloc[0:0].copy()
        platform_results = {
            platform: ProductionDataResult(
                production.copy() if platform == "S2B" else empty.copy(),
                f"{platform} test",
            )
            for platform in DTF_PRODUCTION_PLATFORMS
        }
        batch = BatchProductionResult(production, platform_results, {})

        with TemporaryDirectory() as directory:
            cache_dir = Path(directory)
            with (
                patch("automation.production_cache.CACHE_DIR", cache_dir),
                patch("automation.production_period.CACHE_DIR", cache_dir),
                patch("automation.sync.cache_seed.CACHE_DIR", cache_dir),
                patch(
                    "automation.sync.daily.load_all_clothing_production",
                    return_value=batch,
                ) as fetch,
                patch(
                    "automation.sync.daily._load_credentials",
                    return_value=({}, {}),
                ),
                patch(
                    "automation.sync.daily."
                    "replace_daily_platform_consumption",
                ) as persist,
            ):
                result = sync_production_day(
                    target, supabase=object(), operator="Andy"
                )
                colored_model = load_period_production_model(
                    target, 1, "彩色短袖"
                )
                black_white_model = load_period_production_model(
                    target, 1, "黑白短袖"
                )

        self.assertEqual(result, "completed")
        fetch.assert_called_once()
        self.assertEqual(
            persist.call_count, len(DTF_PRODUCTION_PLATFORMS) * 2
        )
        self.assertTrue(all(
            call.args[2] in {"黑白短袖", "彩色短袖"}
            for call in persist.call_args_list
        ))
        self.assertEqual(colored_model.effective_days, 1)
        self.assertEqual(
            colored_model.data.iloc[0]["平台生产日均"], 10
        )
        self.assertEqual(black_white_model.effective_days, 1)
        self.assertEqual(
            black_white_model.data.iloc[0]["平台生产日均"], 100
        )

    def test_partial_fast_cache_does_not_enter_black_white_period_model(self):
        target = date(2026, 8, 6)
        production = pd.DataFrame([{
            "部门": "DTF", "品类": "黑白短袖", "颜色": "黑",
            "尺码": "L", "数量": 100, "生产项状态": "已完成",
        }])
        with TemporaryDirectory() as directory:
            cache_dir = Path(directory)
            with (
                patch("automation.production_cache.CACHE_DIR", cache_dir),
                patch("automation.production_period.CACHE_DIR", cache_dir),
            ):
                save_production_cache(
                    ALL_CLOTHING_PLATFORMS,
                    target,
                    target,
                    production,
                    "主要平台快速补录",
                    extra_metadata={
                        "included_platforms": [
                            "汉森", "S2B", "SDS1", "SDS2", "Haloo", "隆丰",
                        ],
                        "missing_platforms": ["一朵云"],
                        "is_complete": False,
                        "colored_primary_complete": True,
                    },
                )
                model = load_period_production_model(
                    target, 1, "黑白短袖"
                )

        self.assertEqual(model.effective_days, 0)
        self.assertTrue(model.data.empty)

    def test_recent_model_uses_one_unified_partial_cache_by_category(self):
        current = date(2026, 8, 17)
        start = date(2026, 7, 18)
        end = date(2026, 8, 16)
        rows = pd.DataFrame([
            {
                "部门": "DTF", "品类": "黑白短袖", "颜色": "黑",
                "尺码": "L", "数量": 300, "运营商": "S2B",
            },
            {
                "部门": "DTF", "品类": "彩色短袖", "颜色": "红色",
                "尺码": "M", "数量": 90, "运营商": "SDS2",
            },
        ])
        with TemporaryDirectory() as directory:
            cache_dir = Path(directory)
            with (
                patch("automation.production_cache.CACHE_DIR", cache_dir),
                patch("automation.production_period.CACHE_DIR", cache_dir),
            ):
                save_production_cache(
                    ALL_CLOTHING_PLATFORMS, start, end, rows, "统一生产数据",
                    extra_metadata={
                        "included_platforms": ["S2B"],
                        "available_platforms": ["S2B", "SDS2"],
                        "is_complete": False,
                    },
                )
                black = load_recent_production_model(
                    current, 30, "黑白短袖"
                )
                colored = load_recent_production_model(
                    current, 30, "彩色短袖"
                )

        self.assertEqual(black.total_quantity, 300)
        self.assertEqual(black.data.iloc[0]["平台生产日均"], 10)
        self.assertEqual(colored.total_quantity, 90)
        self.assertEqual(colored.data.iloc[0]["平台生产日均"], 3)
        self.assertEqual(set(colored.available_platforms), {"S2B", "SDS2"})


if __name__ == "__main__":
    unittest.main()
