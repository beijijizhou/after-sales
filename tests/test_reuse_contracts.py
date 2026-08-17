import ast
import unittest
from pathlib import Path

import pandas as pd

from ui.inventory.operations.system_deduction import (
    system_deduction_comparison,
    system_deduction_display,
)
from utils.barcode_patterns import (
    build_exact_search_preview,
    build_fuzzy_search_preview,
)
from utils.option_values import ordered_values, unique_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SharedReuseContractTests(unittest.TestCase):
    def test_unique_values_normalizes_once(self):
        self.assertEqual(
            unique_values([" 白 ", None, "", "黑", "白"]),
            ["白", "黑"],
        )

    def test_ordered_values_uses_available_business_order(self):
        self.assertEqual(
            ordered_values(["5XL", "S", "其他"], ["S", "M", "5XL"]),
            ["S", "5XL", "其他"],
        )

    def test_system_deduction_display_normalizes_signed_columns(self):
        display = system_deduction_display(pd.DataFrame([
            {"状态": "可扣减", "预计扣减": 8, "扣减后库存": 12, "未扣数量": 0},
            {"状态": "库存为 0", "预计扣减": 5, "扣减后库存": 0, "未扣数量": 5},
        ]), eligible_status="可扣减", pending_column="未扣数量")
        self.assertEqual(display["本次出库 (-)"].tolist(), [-8, 0])
        self.assertEqual(display["调整后库存"].tolist(), [12, 0])
        self.assertEqual(display["待处理数量"].tolist(), [0, 5])

    def test_system_deduction_exposes_canonical_stock_contract(self):
        comparison = system_deduction_comparison(pd.DataFrame([{
            "状态": "可扣减", "当前库存": 20,
            "预计扣减": 8, "扣减后库存": 12,
        }]), eligible_status="可扣减")

        self.assertEqual(comparison.loc[0, "本次变动"], -8)
        self.assertEqual(comparison.loc[0, "调整后库存"], 12)

    def test_barcode_preview_builders_share_canonical_schema(self):
        self.assertEqual(
            build_fuzzy_search_preview(["ABC"]),
            [{"原始输入": "ABC", "实际查询内容": "%ABC%"}],
        )
        exact = build_exact_search_preview(["ABC"])
        self.assertEqual(set(exact[0]), {"原始输入", "实际查询内容"})

    def test_pages_do_not_redefine_canonical_option_helpers(self):
        files = (
            "ui/inventory/shared/linked_sku_table.py",
            "ui/inventory/operations/outbound_entry.py",
            "ui/inventory/sales/standalone.py",
            "ui/consumables/page.py",
            "ui/inventory/stock/summary.py",
        )
        forbidden = {"_ordered", "_options", "_unique_values"}
        for relative in files:
            tree = ast.parse((PROJECT_ROOT / relative).read_text())
            names = {
                node.name for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            with self.subTest(file=relative):
                self.assertFalse(names & forbidden)

    def test_deduction_views_import_shared_display_model(self):
        files = (
            "ui/inventory/planning/colored_review.py",
            "ui/inventory/planning/uv_view.py",
            "ui/inventory/dashboard_batch_view.py",
        )
        for relative in files:
            source = (PROJECT_ROOT / relative).read_text()
            with self.subTest(file=relative):
                self.assertIn("system_deduction_comparison", source)
                self.assertIn("render_stock_change_review", source)

    def test_dimension_queries_use_shared_filter_composer(self):
        files = (
            "db/inventory/core/queries.py",
            "db/inventory/container/repository.py",
        )
        for relative in files:
            source = (PROJECT_ROOT / relative).read_text()
            with self.subTest(file=relative):
                self.assertIn("apply_inventory_dimension_filters", source)

    def test_consumable_stocktake_uses_package_validation(self):
        stocktake = (
            PROJECT_ROOT / "ui/consumables/operations/stock_tables.py"
        ).read_text()
        entry = (
            PROJECT_ROOT / "ui/consumables/operations/entry.py"
        ).read_text()
        self.assertIn("validate_package_sizes", stocktake)
        self.assertNotIn("validate_package_sizes", entry)
        self.assertIn("entry_to_base", entry)

    def test_container_posting_has_one_feedback_action(self):
        posting = (PROJECT_ROOT / "ui/inventory/container/posting.py").read_text()
        today = (PROJECT_ROOT / "ui/inventory/container/today.py").read_text()
        events = (PROJECT_ROOT / "ui/inventory/container/events.py").read_text()
        self.assertIn("def post_container_with_feedback", posting)
        self.assertIn("post_container_with_feedback", today)
        self.assertIn("post_container_with_feedback", events)
        self.assertNotIn("post_container_inventory(", today)
        self.assertNotIn("post_container_inventory(", events)


if __name__ == "__main__":
    unittest.main()
