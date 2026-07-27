import unittest

import pandas as pd

from db.inventory.core.packaging import packaging_sku_key
from db.inventory.operations.outbound import convert_packages_to_adjustments
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


if __name__ == "__main__":
    unittest.main()
