import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from automation.sync.uv_daily_operation import (
    PHONE_CASE_PENDING_STATUS,
    apply_daily_sync,
    build_daily_deduction_scope,
    build_phone_case_allocation_preview,
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
            {
                "department": "UV",
                "category": "手机壳",
                "brand": "",
                "material": "磨砂 TPU",
                "color": "",
                "size": "IPHONE 15 PRO",
                "quantity": 1000,
                "is_active": True,
            },
        ])

    @patch(
        "automation.sync.uv_daily_operation.existing_usage",
        return_value=0,
    )
    @patch(
        "automation.sync.uv_daily_operation.existing_phone_case_usage",
        return_value=0,
    )
    def test_preview_separates_phone_case_for_model_allocation(self, _, __):
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
        self.assertEqual(phone["品类"], "手机壳")
        self.assertEqual(phone["状态"], PHONE_CASE_PENDING_STATUS)
        self.assertEqual(phone["当前库存"], 1000)

    def test_phone_case_allocation_builds_model_level_stock_review(self):
        key = "|磨砂 TPU||IPHONE 15 PRO"
        result = build_phone_case_allocation_preview(
            self.inventory, {key: 120}
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["品类"], "手机壳")
        self.assertEqual(result.iloc[0]["型号"], "IPHONE 15 PRO")
        self.assertEqual(result.iloc[0]["当前库存"], 1000)
        self.assertEqual(result.iloc[0]["扣减后库存"], 880)
        self.assertEqual(result.iloc[0]["状态"], "可扣减")

    def test_unallocated_phone_case_does_not_block_production_deduction(self):
        preview = pd.DataFrame([
            {
                "表格产品": "Tie_2030", "当日消耗": 100,
                "预计扣减": 100, "状态": "可扣减",
            },
            {
                "表格产品": "Iphone", "当日消耗": 5,
                "预计扣减": 0, "状态": PHONE_CASE_PENDING_STATUS,
            },
        ])

        ready, pending, blocking = build_daily_deduction_scope(
            preview, pd.DataFrame(), phone_case_complete=False,
        )

        self.assertEqual(ready["表格产品"].tolist(), ["Tie_2030"])
        self.assertEqual(pending["预计扣减"].sum(), 100)
        self.assertTrue(blocking.empty)

    def test_incomplete_phone_case_allocation_is_not_partially_applied(self):
        preview = pd.DataFrame([{
            "表格产品": "Tie_2030", "当日消耗": 100,
            "预计扣减": 100, "状态": "可扣减",
        }])
        allocations = pd.DataFrame([{
            "表格产品": "Iphone", "当日消耗": 3,
            "预计扣减": 3, "状态": "可扣减",
        }])

        ready, _, blocking = build_daily_deduction_scope(
            preview, allocations, phone_case_complete=False,
        )

        self.assertEqual(ready["表格产品"].tolist(), ["Tie_2030"])
        self.assertTrue(blocking.empty)

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
        self.assertTrue(sync_usage.call_args.kwargs["batch_id"])

    @patch(
        "automation.sync.uv_daily_operation.sync_usage_to_inventory",
        return_value=({date(2026, 7, 30): 100}, {}),
    )
    def test_apply_uses_one_batch_for_every_sku(self, sync_usage):
        preview = pd.DataFrame([
            {"表格产品": "Tie_2030", "当日消耗": 100, "状态": "可扣减"},
            {"表格产品": "Tie_1040", "当日消耗": 100, "状态": "可扣减"},
        ])

        apply_daily_sync(
            object(), preview, date(2026, 7, 30), "tester"
        )

        batch_ids = {
            call.kwargs["batch_id"] for call in sync_usage.call_args_list
        }
        self.assertEqual(len(batch_ids), 1)

    @patch(
        "automation.sync.uv_daily_operation.sync_usage_to_inventory",
        return_value=({date(2026, 7, 30): 120}, {}),
    )
    def test_apply_phone_case_uses_selected_material_and_model(self, sync_usage):
        preview = pd.DataFrame([{
            "表格产品": "Iphone", "品类": "手机壳",
            "品牌": "", "材质": "磨砂 TPU", "颜色": "",
            "型号": "IPHONE 15 PRO", "当日消耗": 120,
            "状态": "可扣减",
        }])

        apply_daily_sync(
            object(), preview, date(2026, 7, 30), "tester"
        )

        sku = sync_usage.call_args.args[1]
        self.assertEqual(sku.category, "手机壳")
        self.assertEqual(sku.material, "磨砂 TPU")
        self.assertEqual(sku.size, "IPHONE 15 PRO")


if __name__ == "__main__":
    unittest.main()
