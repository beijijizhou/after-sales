import unittest
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from ui.planning import (
    planning_summary_values,
    render_consumption_window_input,
)


class PlanningUIModelTests(unittest.TestCase):
    def test_shared_consumption_window_offers_presets_and_custom_days(self):
        container = MagicMock()
        container.selectbox.return_value = 60

        result = render_consumption_window_input(
            container, key="usage_window", default_days=30,
        )

        self.assertEqual(result, 60)
        self.assertEqual(
            container.selectbox.call_args.kwargs["options"],
            (30, 60, 90, "自定义"),
        )

        custom = MagicMock()
        custom.selectbox.return_value = "自定义"
        custom.number_input.return_value = 120
        result = render_consumption_window_input(
            custom, key="custom_usage_window", default_days=30,
        )
        self.assertEqual(result, 120)
        self.assertEqual(
            custom.number_input.call_args.kwargs["key"],
            "custom_usage_window_custom",
        )

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
        self.assertIn("render_consumption_window_input", inventory)
        self.assertIn("render_consumption_window_input", consumables)
        self.assertIn("render_planning_summary", consumables)


if __name__ == "__main__":
    unittest.main()
