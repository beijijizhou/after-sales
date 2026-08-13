import unittest

from ui.consumables.units import (
    boxes_to_base,
    entry_to_base,
    entry_unit,
    package_size,
    to_boxes,
    to_entry_quantity,
)


class ConsumableBoxUnitTests(unittest.TestCase):
    def setUp(self):
        self.item = {"package_unit": "箱", "units_per_package": 20}

    def test_box_display_converts_base_inventory(self):
        self.assertEqual(to_boxes(568, self.item), 28.4)

    def test_box_entry_converts_to_ledger_quantity(self):
        self.assertEqual(boxes_to_base(26, self.item), 520)

    def test_only_valid_box_configuration_is_supported(self):
        self.assertEqual(package_size(self.item), 20)
        self.assertIsNone(package_size({"package_unit": "袋", "units_per_package": 20}))

    def test_unpackaged_consumable_uses_base_unit_without_fake_conversion(self):
        item = {"base_unit": "米", "package_unit": None, "units_per_package": None}

        self.assertEqual(entry_unit(item), "米")
        self.assertEqual(entry_to_base(12000, item), 12000)
        self.assertEqual(to_entry_quantity(12000, item), 12000)


if __name__ == "__main__":
    unittest.main()
