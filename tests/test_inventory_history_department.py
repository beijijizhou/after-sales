import unittest

import pandas as pd

from ui.inventory.history.history import filter_history_department
from ui.inventory.history.history_batches import (
    synchronize_batch_selector_state,
)


class InventoryHistoryDepartmentTests(unittest.TestCase):
    def test_batch_selection_resets_when_filtered_category_options_change(self):
        state = {}

        changed = synchronize_batch_selector_state(
            state, "inventory_batch", ["black-latest", "black-old"]
        )
        state["inventory_batch"] = "black-old"
        unchanged = synchronize_batch_selector_state(
            state, "inventory_batch", ["black-latest", "black-old"]
        )
        changed_category = synchronize_batch_selector_state(
            state, "inventory_batch", ["colored-latest", "colored-old"]
        )

        self.assertTrue(changed)
        self.assertFalse(unchanged)
        self.assertTrue(changed_category)
        self.assertEqual(state["inventory_batch"], "colored-latest")

    def test_uv_history_never_contains_dtf_rows(self):
        movements = pd.DataFrame([
            _movement("DTF", "黑白短袖", 10000),
            _movement("UV", "铁板画", -2000),
        ])
        imports = pd.DataFrame(columns=["department"])

        filtered, _, batches = filter_history_department(
            (movements, imports, pd.DataFrame()), "UV"
        )

        self.assertEqual(filtered["department"].tolist(), ["UV"])
        self.assertEqual(batches["部门"].tolist(), ["UV"])


def _movement(department, category, quantity):
    return {
        "department": department,
        "category": category,
        "brand": "",
        "material": "160g" if department == "DTF" else "铁牌",
        "color": "白",
        "size": "2XL" if department == "DTF" else "2030",
        "quantity_change": quantity,
        "quantity_after": abs(quantity),
        "movement_date": "2026-08-06",
        "reason": "临时库存调整",
        "created_at": "2026-08-06T22:05:00+00:00",
        "created_by": "Andy",
        "batch_id": f"{department}-batch",
        "reversal_of_batch_id": None,
        "source_type": "temporary",
    }


if __name__ == "__main__":
    unittest.main()
