import unittest

import pandas as pd

from db.inventory.container.editor import (
    build_posted_container_identity_correction_plan,
    build_posted_container_correction_plan,
)
from ui.inventory.container.item_editor import build_container_item_editor_source
from ui.table_layout import fit_table_height


class ContainerPostedCorrectionTests(unittest.TestCase):
    def test_table_height_expands_for_every_row_without_a_maximum_cap(self):
        self.assertEqual(fit_table_height(range(8)), 318)
        self.assertGreater(fit_table_height(range(100)), 3000)

    def test_editor_sorts_material_brand_color_then_business_size(self):
        identities = [
            ("180g", "Brand B", "Blue", "S"),
            ("160g", "Brand B", "Blue", "M"),
            ("160g", "Brand A", "Red", "XL"),
            ("160g", "Brand A", "Blue", "3XL"),
            ("160g", "Brand A", "Blue", "S"),
            ("160g", "Brand A", "Blue", "5XL"),
            ("160g", "Brand A", "Blue", "2XL"),
            ("160g", "Brand A", "Blue", "L"),
        ]
        rows = [
            {
                "id": str(index),
                "expected_arrival_date": "2026-07-29",
                "category": "黑白短袖",
                "brand": brand,
                "material": material,
                "color": color,
                "size": size,
                "quantity": 1,
                "unit_cost": 1.3,
                "note": "",
            }
            for index, (material, brand, color, size) in enumerate(identities)
        ]

        result = build_container_item_editor_source(pd.DataFrame(rows))

        self.assertEqual(
            list(result[["材质", "品牌", "颜色", "型号"]].itertuples(
                index=False, name=None
            )),
            [
                ("160g", "Brand A", "Blue", "S"),
                ("160g", "Brand A", "Blue", "L"),
                ("160g", "Brand A", "Blue", "2XL"),
                ("160g", "Brand A", "Blue", "3XL"),
                ("160g", "Brand A", "Blue", "5XL"),
                ("160g", "Brand A", "Red", "XL"),
                ("160g", "Brand B", "Blue", "M"),
                ("180g", "Brand B", "Blue", "S"),
            ],
        )

    def test_correction_caps_current_inventory_and_reports_consumed_shortage(self):
        rows = [
            _row("black-s", "黑", "S", 15220),
            _row("white-m", "白", "M", 6348),
        ]
        inventory = [
            {**_sku("黑", "S"), "quantity": 15220},
            {**_sku("白", "M"), "quantity": 0},
        ]

        plan = build_posted_container_correction_plan(
            rows, {"black-s": 14940, "white-m": 6188}, inventory
        )

        self.assertEqual(plan[0]["inventory_change"], -280)
        self.assertEqual(plan[0]["unresolved_shortage"], 0)
        self.assertEqual(plan[1]["inventory_change"], 0)
        self.assertEqual(plan[1]["unresolved_shortage"], 160)

    def test_identity_correction_moves_remaining_stock_without_adding_total(self):
        rows = [{
            "id": "clock", "department": "UV", "category": "木板画",
            "brand": "", "material": "挂钟", "color": "白",
            "size": "25", "quantity": 20_000, "unit_cost": 1.4086,
        }]
        inventory = [
            {**rows[0], "quantity": 26_369},
            {**rows[0], "size": "30", "quantity": 0},
        ]

        plan = build_posted_container_identity_correction_plan(
            rows, {"clock": {"size": "30"}}, inventory
        )

        self.assertEqual(plan[0]["moved_quantity"], 20_000)
        self.assertEqual(plan[0]["unresolved_history"], 0)
        self.assertEqual(plan[0]["target"]["size"], "30")


def _sku(color, size):
    return {
        "department": "DTF", "category": "黑白短袖",
        "brand": "Men's", "material": "160g",
        "color": color, "size": size,
    }


def _row(item_id, color, size, quantity):
    return {"id": item_id, **_sku(color, size), "quantity": quantity}


if __name__ == "__main__":
    unittest.main()
