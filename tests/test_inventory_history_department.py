import unittest

import pandas as pd
from pathlib import Path

from ui.inventory.history.history import (
    filter_movements_for_batches,
    filter_history_department,
)
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

    def test_filtered_view_keeps_every_matching_batch(self):
        movements = pd.DataFrame([
            _movement("DTF", "黑白短袖", -100),
            {
                **_movement("DTF", "黑白短袖", -200),
                "batch_id": "DTF-batch-2",
            },
            _movement("UV", "铁板画", -300),
        ])
        batches = pd.DataFrame({
            "batch_key": ["movement|DTF-batch", "movement|DTF-batch-2"]
        })

        result = filter_movements_for_batches(movements, batches)

        self.assertEqual(result["quantity_change"].tolist(), [-100, -200])

    def test_filtered_history_does_not_expose_internal_batch_key(self):
        source = Path("ui/inventory/history/history.py").read_text(
            encoding="utf-8"
        )

        summary_columns = source.split(
            "def render_filtered_movement_results", 1
        )[1].split("def filter_movements_for_batches", 1)[0]
        self.assertNotIn('"批次", "记录时间"', summary_columns)


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
