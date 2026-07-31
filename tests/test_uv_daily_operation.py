import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from automation.sync.uv_daily_operation import (
    apply_daily_sync,
    build_daily_sync_preview,
)


class UVDailyOperationTests(unittest.TestCase):
    def setUp(self):
        self.inventory = pd.DataFrame([
            {
                "department": "UV",
                "category": "铁板画",
                "brand": "",
                "material": "铁牌",
                "color": "白",
                "size": "2030",
                "quantity": 5000,
            },
            {
                "department": "UV",
                "category": "铁板画",
                "brand": "",
                "material": "铁牌",
                "color": "白",
                "size": "1040",
                "quantity": 100,
            },
        ])

    @patch(
        "automation.sync.uv_daily_operation.existing_usage",
        return_value=0,
    )
    def test_preview_shows_deduction_and_blocks_unknown_product(self, _):
        preview = build_daily_sync_preview(
            object(),
            {"Tie_2030": 2300, "Iphone": 500},
            date(2026, 7, 30),
            self.inventory,
        )

        iron = preview[preview["表格产品"] == "Tie_2030"].iloc[0]
        phone = preview[preview["表格产品"] == "Iphone"].iloc[0]
        self.assertEqual(iron["当前库存"], 5000)
        self.assertEqual(iron["扣减后库存"], 2700)
        self.assertEqual(iron["状态"], "可扣减")
        self.assertEqual(phone["状态"], "待分配 SKU（本次不扣）")

    @patch(
        "automation.sync.uv_daily_operation.existing_usage",
        return_value=2300,
    )
    def test_preview_marks_exact_existing_deduction_as_synced(self, _):
        preview = build_daily_sync_preview(
            object(),
            {"Tie_2030": 2300},
            date(2026, 7, 30),
            self.inventory,
        )

        self.assertEqual(preview.iloc[0]["预计扣减"], 0)
        self.assertEqual(preview.iloc[0]["状态"], "已同步")

    @patch(
        "automation.sync.uv_daily_operation.existing_usage",
        return_value=0,
    )
    def test_preview_blocks_negative_stock(self, _):
        preview = build_daily_sync_preview(
            object(),
            {"Tie_1040": 200},
            date(2026, 7, 30),
            self.inventory,
        )

        self.assertEqual(
            preview.iloc[0]["状态"], "库存不足"
        )
        self.assertEqual(preview.iloc[0]["扣减后库存"], -100)

    @patch(
        "automation.sync.uv_daily_operation.sync_usage_to_inventory",
        return_value=({date(2026, 7, 30): 2300}, {}),
    )
    def test_apply_skips_unassigned_product_and_syncs_mapped_rows(
        self, sync_usage
    ):
        preview = pd.DataFrame([
            {
                "表格产品": "Tie_2030",
                "当日消耗": 2300,
                "状态": "可扣减",
            },
            {
                "表格产品": "Iphone",
                "当日消耗": 1,
                "状态": "待分配 SKU（本次不扣）",
            },
        ])

        imported, skipped = apply_daily_sync(
            object(), preview, date(2026, 7, 30), "tester"
        )

        self.assertEqual((imported, skipped), (2300, 0))
        self.assertEqual(sync_usage.call_count, 1)


if __name__ == "__main__":
    unittest.main()
