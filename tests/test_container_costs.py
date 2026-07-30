import unittest

from db.inventory.container.costs import normalize_container_unit_cost


class ContainerCostTests(unittest.TestCase):
    def test_normalizes_to_four_decimal_places(self):
        self.assertEqual(normalize_container_unit_cost("1.23456"), 1.2346)

    def test_rejects_negative_cost(self):
        with self.assertRaisesRegex(ValueError, "不能小于"):
            normalize_container_unit_cost(-0.01)

    def test_rejects_invalid_cost(self):
        with self.assertRaisesRegex(ValueError, "有效数字"):
            normalize_container_unit_cost("unknown")


if __name__ == "__main__":
    unittest.main()
