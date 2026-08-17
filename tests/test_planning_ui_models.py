import unittest
from pathlib import Path

import pandas as pd

from ui.planning import planning_summary_values


class PlanningUIModelTests(unittest.TestCase):
    def test_summary_uses_one_contract_for_inventory_and_consumables(self):
        inventory = planning_summary_values(
            pd.DataFrame([
                {"建议": 100, "可撑": 5, "在途后": 40},
                {"建议": 0, "可撑": 20, "在途后": 0},
            ]),
            reorder_column="建议",
            coverage_column="可撑",
            after_incoming_column="在途后",
        )
        consumables = planning_summary_values(
            pd.DataFrame([
                {"建议": 10, "可撑": 3, "单位": "卷"},
                {"建议": 20, "可撑": 4, "单位": "瓶"},
            ]),
            reorder_column="建议",
            coverage_column="可撑",
            unit_column="单位",
        )

        self.assertEqual(inventory["reorder_skus"], 1)
        self.assertEqual(inventory["after_incoming_total"], 40)
        self.assertEqual(consumables["reorder_skus"], 2)
        self.assertEqual(consumables["units"], ["卷", "瓶"])

    def test_inventory_and_consumables_use_shared_planning_components(self):
        root = Path(__file__).resolve().parents[1]
        inventory = (
            root / "ui/inventory/planning/consumption.py"
        ).read_text()
        consumables = (root / "ui/consumables/planning.py").read_text()
        self.assertIn("render_target_days_input", inventory)
        self.assertIn("render_target_days_input", consumables)
        self.assertIn("render_planning_summary", consumables)


if __name__ == "__main__":
    unittest.main()
