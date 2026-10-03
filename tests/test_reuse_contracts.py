import ast
import unittest
from pathlib import Path

import pandas as pd

from ui.inventory.operations.system_deduction import (
    system_deduction_comparison,
    system_deduction_display,
)
from utils.barcode_patterns import (
    build_order_code_to_inputs,
    embedded_order_inputs,
    build_barcode_candidates,
    build_barcode_prefixes,
    build_exact_search_preview,
    build_fuzzy_search_preview,
)
from utils.hansen_matcher import extract_order_key
from utils.option_values import ordered_values, unique_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SharedReuseContractTests(unittest.TestCase):
    def test_project_guide_requires_actor_and_time_for_every_mutation(self):
        guide = (PROJECT_ROOT / "AGENTS.md").read_text()

        self.assertIn(
            "Every business mutation must record who performed it and when",
            guide,
        )
        self.assertIn("what happened, who did it, and when", guide)
        self.assertIn("legacy event predates audit", guide)

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
            build_fuzzy_search_preview(["ABCD"]),
            [
                {"原始输入": "ABCD", "实际查询内容": "ABCD"},
                {"原始输入": "ABCD", "实际查询内容": "ABCD*"},
            ],
        )
        exact = build_exact_search_preview(["ABC"])
        self.assertEqual(set(exact[0]), {"原始输入", "实际查询内容"})

    def test_humbird_main_order_expands_multi_item_variants(self):
        self.assertEqual(
            build_barcode_prefixes("BVF3J2C"),
            ["SCGD-BVF3J2C-"],
        )

    def test_humbird_multi_digit_item_expands_a_and_b(self):
        self.assertEqual(
            build_barcode_candidates("BVF3J2C-15"),
            ["SCGD-BVF3J2C-15-A", "SCGD-BVF3J2C-15-B"],
        )

    def test_s2b_main_order_expands_multiple_items(self):
        self.assertEqual(
            build_barcode_prefixes("WPG6SJ"),
            ["WPG6SJ-"],
        )

    def test_hansen_fuzzy_prefix_includes_reprint_suffixes(self):
        self.assertEqual(
            build_barcode_prefixes("LB26092550140"),
            ["LB26092550140,"],
        )
        self.assertEqual(
            build_barcode_prefixes("LB26092550140", fuzzy=True),
            ["LB26092550140"],
        )

    def test_malformed_humbird_and_s2b_scans_match_only_searched_item(self):
        inputs = ["BYRU77Z-1", "BYRU77Z-2", "XB7KQQ", "XB7KQQ-2"]
        codes = build_order_code_to_inputs(inputs)
        self.assertEqual(
            embedded_order_inputs("cSCGD-BYRU77Z-1-A", codes),
            ["BYRU77Z-1"],
        )
        self.assertEqual(embedded_order_inputs("cXB7KQQ-3", codes), ["XB7KQQ"])
        self.assertEqual(
            embedded_order_inputs("bmapvrm-1", {"BMAPVRM": ["BMAPVRM"]}),
            ["BMAPVRM"],
        )

    def test_hansen_order_key_is_extracted_from_composite_scan(self):
        self.assertEqual(
            extract_order_key(
                "internIntern123*LB26100250808,1,1,2XL,White,CVC,end"
            ),
            "LB26100250808",
        )
        self.assertEqual(
            extract_order_key("LB26092660135E1,1,1,L,Black,CVC,end"),
            "LB26092660135E1",
        )

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
        self.assertIn("render_container_posting_action", today)
        self.assertIn("post_container_with_feedback", events)
        self.assertNotIn("post_container_inventory(", today)
        self.assertNotIn("post_container_inventory(", events)


if __name__ == "__main__":
    unittest.main()
