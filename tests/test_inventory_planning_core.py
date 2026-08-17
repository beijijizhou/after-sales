from datetime import date
import unittest

from db.planning import (
    calculate_arrival_plan,
    calculate_stock_plan,
    classify_inventory_plan,
)


class InventoryPlanningCoreTests(unittest.TestCase):
    def test_same_base_unit_inputs_share_one_reorder_contract(self):
        apparel = calculate_stock_plan(30, 10, target_days=14)
        consumable = calculate_stock_plan(
            30, 10, target_days=14, package_size=20
        )

        self.assertEqual(apparel.coverage_days, 3)
        self.assertEqual(apparel.reorder_quantity, 110)
        self.assertEqual(consumable.reorder_quantity, 110)
        self.assertEqual(consumable.reorder_packages, 5.5)

    def test_minimum_stock_can_raise_reorder_target(self):
        plan = calculate_stock_plan(
            30, 1, target_days=14, minimum_quantity=50
        )

        self.assertEqual(plan.target_quantity, 50)
        self.assertEqual(plan.reorder_quantity, 20)

    def test_elapsed_days_use_estimated_current_stock(self):
        plan = calculate_stock_plan(
            100, 10, target_days=14, elapsed_days=3
        )

        self.assertEqual(plan.estimated_current_quantity, 70)
        self.assertEqual(plan.coverage_days, 7)
        self.assertEqual(plan.reorder_quantity, 70)

    def test_multiple_arrivals_preserve_intermediate_shortage(self):
        plan = calculate_arrival_plan(
            20,
            10,
            [
                (date(2026, 8, 22), 100),
                (date(2026, 8, 27), 200),
            ],
            date(2026, 8, 17),
        )

        self.assertEqual(plan.days_to_first_arrival, 5)
        self.assertEqual(plan.quantity_before_first_arrival, 0)
        self.assertEqual(plan.shortage_before_arrivals, 30)
        self.assertEqual(plan.quantity_after_all_arrivals, 220)
        self.assertEqual(plan.coverage_after_all_arrivals, 22)

    def test_zero_usage_keeps_stock_visible_without_fake_coverage(self):
        plan = calculate_arrival_plan(
            25, 0, [(date(2026, 8, 18), 10)], date(2026, 8, 17)
        )

        self.assertEqual(plan.quantity_before_first_arrival, 25)
        self.assertEqual(plan.quantity_after_all_arrivals, 35)
        self.assertIsNone(plan.coverage_after_all_arrivals)
        self.assertEqual(plan.shortage_before_arrivals, 0)

    def test_status_contract_is_category_neutral(self):
        status = classify_inventory_plan(
            has_arrivals=True,
            is_arrived=False,
            days_to_arrival=5,
            daily_usage=10,
            coverage_days=2,
            shortage=30,
            coverage_after_arrival=12,
        )

        self.assertEqual(status, "到货前可能断货")


if __name__ == "__main__":
    unittest.main()
