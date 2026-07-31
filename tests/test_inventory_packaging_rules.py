import unittest

import pandas as pd

from db.inventory.core.packaging import (
    packaging_material_key,
    packaging_sku_key,
)
from db.inventory.operations.outbound import (
    build_outbound_package_template,
    convert_packages_to_adjustments,
    extract_size_box_units,
)
from ui.inventory.operations.outbound_i18n import (
    to_display_table,
    to_internal_table,
)
class InventoryPackagingRuleTests(unittest.TestCase):
    def test_custom_table_rule_overrides_default_box_units(self):
        packages = pd.DataFrame([{
            "日期": pd.Timestamp("2026-07-26").date(),
            "包装规格": "180g/Haloo/Box",
            "颜色": "黑",
            "S": 2,
            "M": 0,
            "L": 0,
            "XL": 0,
            "2XL": 0,
            "3XL": 0,
            "4XL": 0,
            "5XL": 0,
            "备注": "每日正常出货",
        }])
        rules = {"standard_box": 80}

        result = convert_packages_to_adjustments(packages, rules)

        self.assertEqual(result.loc[0, "数量"], 160)

    def test_missing_rule_keeps_existing_default(self):
        packages = pd.DataFrame([{
            "日期": pd.Timestamp("2026-07-26").date(),
            "包装规格": "160g/Mens/Box",
            "颜色": "黑",
            "S": 1,
            "M": 0,
            "L": 0,
            "XL": 0,
            "2XL": 0,
            "3XL": 0,
            "4XL": 0,
            "5XL": 0,
            "备注": "每日正常出货",
        }])

        result = convert_packages_to_adjustments(packages)

        self.assertEqual(result.loc[0, "数量"], 100)

    def test_sku_rule_takes_priority_over_general_rule(self):
        packages = pd.DataFrame([{
            "日期": pd.Timestamp("2026-07-26").date(),
            "包装规格": "180g/Haloo/Box",
            "颜色": "黑",
            "S": 1,
            "M": 0,
            "L": 0,
            "XL": 0,
            "2XL": 0,
            "3XL": 0,
            "4XL": 0,
            "5XL": 0,
            "备注": "每日正常出货",
        }])
        sku_rules = {
            packaging_sku_key(
                "Haloo", "180g", "黑", "S", "Box"
            ): 90
        }

        result = convert_packages_to_adjustments(
            packages,
            {"standard_box": 80},
            sku_rules,
        )

        self.assertEqual(result.loc[0, "数量"], 90)

    def test_material_rule_takes_priority_over_sku_rule(self):
        packages = pd.DataFrame([{
            "日期": pd.Timestamp("2026-07-26").date(),
            "包装规格": "180g/Haloo/Box", "颜色": "黑",
            "S": 1, "M": 0, "L": 0, "XL": 0,
            "2XL": 0, "3XL": 0, "4XL": 0, "5XL": 0,
            "备注": "每日正常出货",
        }])
        special_rules = {
            packaging_material_key("180g", "Box"): 70,
            packaging_sku_key(
                "Haloo", "180g", "黑", "S", "Box"
            ): 90,
        }

        result = convert_packages_to_adjustments(
            packages, {"standard_box": 80}, special_rules
        )

        self.assertEqual(result.loc[0, "数量"], 70)

    def test_container_note_extracts_mixed_box_units_for_size(self):
        note = "发票26071701；L 264箱×72件；3XL 3箱×70件+3箱×72件"

        self.assertEqual(extract_size_box_units(note, "L"), [72])
        self.assertEqual(extract_size_box_units(note, "3XL"), [70, 72])

    def test_container_package_units_override_other_rules(self):
        packages = pd.DataFrame([{
            "日期": pd.Timestamp("2026-07-31").date(),
            "包装规格": "160g/Caribbean/Box/70件", "颜色": "白",
            "S": 0, "M": 0, "L": 0, "XL": 0,
            "2XL": 0, "3XL": 2, "4XL": 0, "5XL": 0,
            "备注": "仓库每日出货",
        }])
        specs = {
            "160g/Caribbean/Box/70件": (
                "Caribbean", "160g", "Box", 70
            )
        }

        result = convert_packages_to_adjustments(
            packages,
            {"standard_box": 80},
            {packaging_material_key("160g", "Box"): 90},
            specs,
        )

        self.assertEqual(result.loc[0, "数量"], 140)

    def test_dynamic_container_spec_survives_chinese_translation(self):
        source = pd.DataFrame([{
            "包装规格": "160g/Caribbean/Box/70件",
            "颜色": "白", "备注": "每日正常出货",
        }])

        restored = to_internal_table(
            to_display_table(source, "zh"), "zh"
        )

        self.assertEqual(
            restored.loc[0, "包装规格"],
            "160g/Caribbean/Box/70件",
        )

    def test_container_specs_can_be_listed_before_defaults(self):
        specs = {
            "160g/Caribbean/Box/70件": (
                "Caribbean", "160g", "Box", 70
            ),
            "180g/Haloo/Box": ("Haloo", "180g", "Box"),
        }

        result = build_outbound_package_template(specs)

        self.assertEqual(
            result.loc[0, "包装规格"],
            "160g/Caribbean/Box/70件",
        )


if __name__ == "__main__":
    unittest.main()
