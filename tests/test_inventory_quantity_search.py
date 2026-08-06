from datetime import date
import unittest

import pandas as pd

from ui.inventory.history.quantity_search import (
    find_outbound_quantity_candidates,
    outbound_movements_for_date,
    parse_quantity_search,
)


def movement(
    quantity, movement_date="2026-08-05", batch_id="batch-a",
    color="黑", size="L",
):
    return {
        "department": "DTF",
        "category": "黑白短袖",
        "brand": "Caribbean",
        "material": "180g",
        "color": color,
        "size": size,
        "quantity_change": quantity,
        "movement_date": movement_date,
        "reason": "临时库存调整：别人拉走",
        "created_at": f"{movement_date}T15:00:00+00:00",
        "created_by": "Andy",
        "batch_id": batch_id,
        "reversal_of_batch_id": None,
    }


class InventoryQuantitySearchTests(unittest.TestCase):
    def test_accepts_commas_in_quantity(self):
        self.assertEqual(parse_quantity_search("20,000"), 20000)
        self.assertIsNone(parse_quantity_search("黑色两万"))

    def test_matches_outbound_batch_total_with_tolerance(self):
        rows = pd.DataFrame([
            movement(-11_000, size="L"),
            movement(-9_500, size="XL"),
            movement(-5_000, batch_id="batch-b", color="白"),
        ])

        result = find_outbound_quantity_candidates(rows, 20_000, 1_000)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["匹配口径"], "批次合计")
        self.assertEqual(int(result.iloc[0]["匹配数量"]), 20_500)
        self.assertEqual(result.iloc[0]["颜色"], "黑")

    def test_matches_single_sku_when_batch_total_is_larger(self):
        rows = pd.DataFrame([
            movement(-19_800, size="L"),
            movement(-8_000, size="XL"),
        ])

        result = find_outbound_quantity_candidates(rows, 20_000, 500)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["匹配口径"], "单个 SKU")
        self.assertEqual(int(result.iloc[0]["批次出库合计"]), 27_800)

    def test_matches_same_day_total_across_multiple_batches(self):
        rows = pd.DataFrame([
            movement(-10_492, batch_id="batch-a"),
            movement(-6_984, batch_id="batch-b"),
            movement(
                -5_000, movement_date="2026-08-04", batch_id="batch-c"
            ),
        ])

        result = find_outbound_quantity_candidates(rows, 20_000, 3_000)

        daily = result[result["匹配口径"] == "当日合计"]
        self.assertEqual(len(daily), 1)
        self.assertEqual(int(daily.iloc[0]["匹配数量"]), 17_476)
        self.assertEqual(str(daily.iloc[0]["日期"]), "2026-08-05")

    def test_matches_two_sizes_in_the_same_larger_batch(self):
        rows = pd.DataFrame([
            movement(-10_202, size="XL"),
            movement(-10_072, size="2XL"),
            movement(-4_000, size="S"),
            movement(-3_200, size="M"),
        ])

        result = find_outbound_quantity_candidates(rows, 20_000, 3_000)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["匹配口径"], "两个 SKU 合计")
        self.assertEqual(int(result.iloc[0]["匹配数量"]), 20_274)
        self.assertEqual(int(result.iloc[0]["批次出库合计"]), 27_474)

    def test_selected_date_returns_every_outbound_row_for_that_day(self):
        rows = pd.DataFrame([
            movement(-20_000, color="黑"),
            movement(-3_000, batch_id="batch-b", color="白"),
            movement(1_000, batch_id="batch-c", color="黑"),
            movement(
                -4_000, movement_date="2026-08-04",
                batch_id="batch-d", color="黑",
            ),
        ])

        result = outbound_movements_for_date(rows, date(2026, 8, 5))

        self.assertEqual(len(result), 2)
        self.assertEqual(set(result["color"]), {"黑", "白"})
        self.assertTrue(result["quantity_change"].lt(0).all())


if __name__ == "__main__":
    unittest.main()
