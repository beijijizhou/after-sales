import unittest
from unittest.mock import patch
import pandas as pd

from utils.erp.catalog import normalize_color
from automation.sync.dtf_colored_inventory import (
    build_colored_consumption_wide_table,
    build_colored_forecast_usage,
    build_colored_platform_audit,
    build_colored_reconciliation_backlog,
    load_colored_consumption_history,
    _cap_allocation_at_zero,
)


class ColoredProductionInventoryTests(unittest.TestCase):
    def test_reconciliation_backlog_separates_processed_daily_difference(self):
        target = pd.Timestamp("2026-08-06").date()
        source = pd.DataFrame([{
            "运营商": "S2B", "颜色": "红色", "尺码": "L",
            "生产数量": 100, "生产记录数": 80,
        }])
        preview = pd.DataFrame([{
            "状态": "可扣减", "预计扣减": 20, "未扣数量": 0,
        }, {
            "状态": "库存为 0（待清点）", "预计扣减": 0,
            "未扣数量": 10,
        }])
        with (
            patch(
                "automation.sync.dtf_colored_inventory."
                "load_daily_colored_production_source",
                side_effect=lambda day: (
                    (source, {"missing_platforms": ["Haloo"]})
                    if day == target else (pd.DataFrame(), {})
                ),
            ),
            patch(
                "automation.sync.dtf_colored_inventory."
                "load_colored_day_deducted_total", return_value=70,
            ),
            patch(
                "automation.sync.dtf_colored_inventory."
                "build_colored_daily_preview", return_value=preview,
            ),
        ):
            result = build_colored_reconciliation_backlog(
                object(), target, days=2
            )

        self.assertEqual(result.iloc[0]["已扣库存"], 70)
        self.assertEqual(result.iloc[0]["当前可补扣"], 20)
        self.assertEqual(result.iloc[0]["库存/SKU待核对"], 10)
        self.assertEqual(result.iloc[0]["尚未读取平台"], "Haloo")

    def test_fast_platform_cache_enters_colored_consumption_model(self):
        target = pd.Timestamp("2026-08-06").date()
        fast_daily = pd.DataFrame([
            {"颜色": "红色", "尺码": "L", "生产数量": 120},
        ])

        with patch(
            "automation.sync.dtf_colored_inventory."
            "load_daily_colored_production",
            side_effect=lambda day, require_complete=False: (
                fast_daily if day == target else pd.DataFrame()
            ),
        ) as load_daily:
            result = load_colored_consumption_history(
                object(), target, days=2
            )

        self.assertEqual(result.iloc[0]["每日消耗"], 120)
        self.assertEqual(result.iloc[0]["有效天数"], 1)
        self.assertTrue(all(
            call.kwargs["require_complete"] is False
            for call in load_daily.call_args_list
        ))

    def test_golden_maps_to_yellow(self):
        self.assertEqual(normalize_color("golden"), "黄色")

    def test_shortage_is_capped_at_zero(self):
        allocation = pd.DataFrame([{
            "品牌": "未匹配库存", "材质": "", "颜色": "粉色", "尺码": "S",
            "当前库存": 0, "预计扣减": 93, "扣减后库存": -93, "状态": "库存不足",
        }])
        preview = _cap_allocation_at_zero(pd.DataFrame(columns=["映射状态"]), allocation)
        self.assertEqual(preview.iloc[0]["预计扣减"], 0)
        self.assertEqual(preview.iloc[0]["扣减后库存"], 0)
        self.assertEqual(preview.iloc[0]["未扣数量"], 93)

    def test_missing_sku_remains_blocking(self):
        allocation = pd.DataFrame([{
            "品牌": "未匹配库存", "材质": "", "颜色": "绿色", "尺码": "5XL",
            "当前库存": 0, "预计扣减": 1, "扣减后库存": -1, "状态": "库存不足",
        }])
        preview = _cap_allocation_at_zero(
            pd.DataFrame(columns=["映射状态"]), allocation,
        )
        self.assertEqual(preview.iloc[0]["状态"], "库存为 0（待清点）")

    def test_colored_history_builds_container_forecast_usage(self):
        history = pd.DataFrame([{
            "颜色": "红色", "尺码": "L",
            "每日消耗": 123.5, "有效天数": 13,
        }])
        usage = build_colored_forecast_usage(history)
        row = usage.iloc[0]
        self.assertEqual(row["department"], "DTF")
        self.assertEqual(row["category"], "彩色短袖")
        self.assertEqual(row["planning_material"], "全部品牌/材质")
        self.assertEqual(row["system_daily_usage"], 123.5)

    def test_colored_consumption_is_pivoted_to_size_columns(self):
        display = pd.DataFrame([
            {"颜色": "TiffanyBlue", "尺码": "S", "每日消耗": 0.846,
             "当前库存": 2711, "可撑天数": 3203.909},
            {"颜色": "TiffanyBlue", "尺码": "L", "每日消耗": 2.308,
             "当前库存": 2824, "可撑天数": 1223.733},
        ])
        wide = build_colored_consumption_wide_table(display)
        self.assertEqual(len(wide), 3)
        daily = wide[wide["指标"] == "每日消耗"].iloc[0]
        stock = wide[wide["指标"] == "当前库存"].iloc[0]
        self.assertEqual(daily["S"], 0.8)
        self.assertEqual(daily["L"], 2.3)
        self.assertEqual(stock["S"], 2711.0)
        self.assertIsNone(daily["M"])

    def test_platform_audit_lists_zero_and_missing_sources(self):
        detail = pd.DataFrame([
            {"运营商": "汉森", "颜色": "红色", "尺码": "L",
             "生产数量": 421, "生产记录数": 278},
            {"运营商": "SDS1", "颜色": "蓝色", "尺码": "M",
             "生产数量": 175, "生产记录数": 175},
        ])
        metadata = {
            "included_platforms": ["汉森", "SDS1", "一朵云"],
            "missing_platforms": ["S2B"],
        }
        with patch(
            "automation.sync.dtf_colored_inventory."
            "load_daily_colored_production_source",
            return_value=(detail, metadata),
        ):
            result, returned_metadata = build_colored_platform_audit(
                pd.Timestamp("2026-08-02").date()
            )

        indexed = result.set_index("平台")
        self.assertEqual(indexed.loc["汉森", "原始生产件数"], 421)
        self.assertEqual(indexed.loc["一朵云", "原始生产件数"], 0)
        self.assertEqual(indexed.loc["一朵云", "读取状态"], "已读取")
        self.assertEqual(indexed.loc["S2B", "读取状态"], "读取失败/缺失")
        self.assertEqual(returned_metadata, metadata)


if __name__ == "__main__":
    unittest.main()
