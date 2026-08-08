import unittest
from unittest.mock import patch

import pandas as pd

from ui.inventory.category_routing import is_consumable_category
from ui.inventory.operations import pages


class InventoryCategoryRoutingTests(unittest.TestCase):
    def test_dtf_consumable_labels_use_consumable_workflow(self):
        self.assertTrue(is_consumable_category("DTF耗材"))
        self.assertTrue(is_consumable_category("DTF 耗材"))

    def test_production_categories_keep_inventory_workflow(self):
        self.assertFalse(is_consumable_category("黑白短袖"))
        self.assertFalse(is_consumable_category("彩色短袖"))
        self.assertFalse(is_consumable_category("UV 铁板画"))

    @patch.object(pages, "render_adjust_form")
    @patch.object(pages, "render_inventory_unit_calculator")
    @patch.object(pages, "_render_consumable_movement_operation")
    def test_temporary_adjustment_routes_consumables_to_consumable_form(
        self, render_consumables, render_calculator, render_adjustment,
    ):
        pages.render_temporary_movement_operation(
            object(),
            "DTF",
            "DTF耗材",
            pd.DataFrame(),
            pd.DataFrame(columns=["品类"]),
            True,
        )

        render_consumables.assert_called_once()
        render_calculator.assert_not_called()
        render_adjustment.assert_not_called()


if __name__ == "__main__":
    unittest.main()
