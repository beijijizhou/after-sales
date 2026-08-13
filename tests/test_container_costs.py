import unittest

from db.inventory.container.costs import (
    build_posted_container_cost_plan,
    normalize_container_unit_cost,
)


class ContainerCostTests(unittest.TestCase):
    def test_normalizes_to_four_decimal_places(self):
        self.assertEqual(normalize_container_unit_cost("1.23456"), 1.2346)

    def test_rejects_negative_cost(self):
        with self.assertRaisesRegex(ValueError, "不能小于"):
            normalize_container_unit_cost(-0.01)

    def test_rejects_invalid_cost(self):
        with self.assertRaisesRegex(ValueError, "有效数字"):
            normalize_container_unit_cost("unknown")

    def test_posted_cost_plan_keeps_quantity_and_changes_only_cost(self):
        rows = [{
            "id": "row-1", "department": "UV", "category": "铁板画",
            "brand": "", "material": "铁牌", "color": "白",
            "size": "2030", "quantity": 1000, "unit_cost": 0.607,
        }]

        result = build_posted_container_cost_plan(
            rows, {"row-1": 0.65}
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["quantity"], 1000)
        self.assertEqual(result[0]["old_unit_cost"], 0.607)
        self.assertEqual(result[0]["new_unit_cost"], 0.65)

    def test_posted_cost_plan_rejects_conflicting_costs_for_same_sku(self):
        identity = {
            "department": "UV", "category": "铁板画", "brand": "",
            "material": "铁牌", "color": "白", "size": "2030",
            "quantity": 500, "unit_cost": 0.607,
        }
        rows = [
            {"id": "row-1", **identity},
            {"id": "row-2", **identity},
        ]

        with self.assertRaisesRegex(ValueError, "同一 SKU"):
            build_posted_container_cost_plan(
                rows, {"row-1": 0.65, "row-2": 0.66}
            )


if __name__ == "__main__":
    unittest.main()
