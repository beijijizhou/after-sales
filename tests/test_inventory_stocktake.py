import unittest
from datetime import date
from unittest.mock import Mock

import pandas as pd

from db.inventory.operations.adjustments import (
    apply_adjustment_rows,
    apply_stocktake_rows,
    normalize_adjustment_rows,
)


class InventoryStocktakeTests(unittest.TestCase):
    def test_hoodie_add_inventory_uses_style_aware_rpc(self):
        supabase = Mock()
        supabase.rpc.return_value.execute.return_value.data = "hoodie-add"
        rows = pd.DataFrame([{
            "日期": date(2026, 10, 1), "操作": "增加",
            "品牌": "Haloo", "材质": "连帽", "款式": "常规",
            "颜色": "黑", "尺码": "M", "数量": 100,
            "成本": pd.NA, "备注": "卫衣到货",
        }])

        with unittest.mock.patch(
            "db.inventory.operations.adjustments.create_inventory_snapshot"
        ):
            apply_adjustment_rows(
                supabase, "DTF", "卫衣", rows, "Andy", batch_id="hoodie-add"
            )

        rpc_name, parameters = supabase.rpc.call_args.args
        self.assertEqual(rpc_name, "apply_inventory_adjustment_batch_with_style")
        self.assertEqual(parameters["p_rows"][0]["style"], "常规")
        self.assertEqual(parameters["p_rows"][0]["quantity_change"], 100)

    def test_hoodie_deduct_inventory_uses_style_aware_rpc(self):
        supabase = Mock()
        supabase.rpc.return_value.execute.return_value.data = "hoodie-deduct"
        rows = pd.DataFrame([{
            "日期": date(2026, 10, 1), "操作": "扣减",
            "品牌": "Haloo", "材质": "连帽", "款式": "常规",
            "颜色": "白", "尺码": "XL", "数量": 12,
            "成本": pd.NA, "备注": "每日出库",
        }])

        with unittest.mock.patch(
            "db.inventory.operations.adjustments.create_inventory_snapshot"
        ):
            apply_adjustment_rows(
                supabase, "DTF", "卫衣", rows, "Andy",
                batch_id="hoodie-deduct",
            )

        _, parameters = supabase.rpc.call_args.args
        self.assertEqual(parameters["p_rows"][0]["style"], "常规")
        self.assertEqual(parameters["p_rows"][0]["quantity_change"], -12)

    def test_wide_stocktake_keeps_zero_targets_for_selected_row(self):
        source = pd.DataFrame([{
            "日期": date(2026, 8, 10), "操作": "设置",
            "设置此行": True, "品牌": "Men's", "材质": "160g",
            "颜色": "白", "S": 4320, "M": 0, "L": 0, "XL": 0,
            "2XL": 1500, "3XL": 180, "4XL": 2560, "5XL": 5840,
            "备注": "08/10 盘点",
        }])

        result = normalize_adjustment_rows(source)

        self.assertEqual(len(result), 8)
        self.assertEqual(result.set_index("尺码").loc["M", "数量"], 0)
        self.assertEqual(result["数量"].sum(), 14400)

    def test_stocktake_calls_dedicated_audited_rpc_with_targets(self):
        supabase = Mock()
        supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{
            "brand": "Caribbean", "material": "160g",
            "color": "白", "size": "L",
        }]
        supabase.rpc.return_value.execute.return_value.data = "batch-1"
        rows = pd.DataFrame([{
            "日期": date(2026, 8, 10), "操作": "设置",
            "品牌": "Caribbean", "材质": "160g", "颜色": "白",
            "尺码": "L", "数量": 20360, "备注": "08/10 盘点",
        }])

        with unittest.mock.patch(
            "db.inventory.operations.adjustments.create_inventory_snapshot"
        ):
            result = apply_stocktake_rows(
                supabase, "DTF", "黑白短袖", rows, "Andy", "batch-1"
            )

        self.assertEqual(result, "batch-1")
        rpc_name, parameters = supabase.rpc.call_args.args
        self.assertEqual(rpc_name, "apply_inventory_stocktake_batch")
        self.assertEqual(parameters["p_rows"][0]["target_quantity"], 20360)

    def test_hoodie_stocktake_keeps_style_in_sku_identity(self):
        supabase = Mock()
        supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{
            "brand": "Haloo", "material": "连帽", "style": "常规",
            "color": "黑", "size": "M",
        }]
        supabase.rpc.return_value.execute.return_value.data = "hoodie-batch"
        rows = pd.DataFrame([{
            "日期": date(2026, 10, 1), "操作": "设置",
            "品牌": "Haloo", "材质": "连帽", "款式": "常规",
            "颜色": "黑", "尺码": "M", "数量": 500, "备注": "盘点",
        }])

        with unittest.mock.patch(
            "db.inventory.operations.adjustments.create_inventory_snapshot"
        ):
            apply_stocktake_rows(
                supabase, "DTF", "卫衣", rows, "Andy", "hoodie-batch"
            )

        parameters = supabase.rpc.call_args.args[1]
        self.assertEqual(parameters["p_rows"][0]["style"], "常规")
        self.assertEqual(parameters["p_rows"][0]["target_quantity"], 500)

    def test_stocktake_skips_missing_sku_when_target_is_zero(self):
        supabase = Mock()
        supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{
            "brand": "Caribbean", "material": "160g",
            "color": "白", "size": "L",
        }]
        supabase.rpc.return_value.execute.return_value.data = "batch-2"
        rows = pd.DataFrame([
            {
                "日期": date(2026, 8, 10), "品牌": "Caribbean",
                "材质": "160g", "颜色": "白", "尺码": "S",
                "数量": 0, "备注": "盘点",
            },
            {
                "日期": date(2026, 8, 10), "品牌": "Caribbean",
                "材质": "160g", "颜色": "白", "尺码": "L",
                "数量": 20360, "备注": "盘点",
            },
        ])

        with unittest.mock.patch(
            "db.inventory.operations.adjustments.create_inventory_snapshot"
        ):
            apply_stocktake_rows(
                supabase, "DTF", "黑白短袖", rows, "Andy", "batch-2"
            )

        parameters = supabase.rpc.call_args.args[1]
        self.assertEqual(len(parameters["p_rows"]), 1)
        self.assertEqual(parameters["p_rows"][0]["size"], "L")


if __name__ == "__main__":
    unittest.main()
