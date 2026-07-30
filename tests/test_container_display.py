import unittest
from datetime import date

import pandas as pd

from db.inventory.container.tables import (
    build_container_display,
    build_container_inventory_summary,
)
from ui.inventory.container.tables import calculate_container_totals


def container_row(department, material, item, quantity):
    return {
        "container_key": "9柜",
        "shipped_date": date(2026, 6, 5),
        "expected_arrival_date": date(2026, 7, 20),
        "actual_arrival_date": date(2026, 7, 28),
        "actual_arrival_at": "2026-07-28T15:30:00-04:00",
        "container_no": "9柜",
        "department": department,
        "category": "铁板画" if department == "UV" else "黑白短袖",
        "brand": "",
        "material": material,
        "color": "白",
        "size": item,
        "quantity": quantity,
        "status": "已到货",
        "note": "",
    }


class ContainerDisplayTests(unittest.TestCase):
    def test_uv_uses_compact_model_rows(self):
        source = pd.DataFrame([
            container_row("UV", "铁牌", "1040", 20_000),
            container_row("UV", "铝牌", "YUAN", 20_100),
        ])

        display = build_container_display(source)

        self.assertEqual(display["型号"].tolist(), ["1040", "YUAN"])
        self.assertEqual(display["数量"].tolist(), [20_000, 20_100])
        self.assertEqual(
            display.loc[0, "实际到货时间（纽约）"],
            "2026-07-28 15:30:00",
        )
        self.assertNotIn("S", display.columns)
        self.assertNotIn("5XL", display.columns)

    def test_dtf_keeps_size_columns(self):
        source = pd.DataFrame([
            container_row("DTF", "180g", "S", 72),
        ])

        display = build_container_display(source)

        self.assertEqual(display.loc[0, "S"], 72)
        self.assertNotIn("型号", display.columns)

    def test_container_totals_include_every_cost_group(self):
        source = pd.DataFrame([
            {
                **container_row("DTF", "160g", "L", 19_008),
                "unit_cost": 1.38,
            },
            {
                **container_row("DTF", "160g", "4XL", 3_500),
                "unit_cost": 1.88,
            },
        ])
        display = build_container_display(source, include_cost=True)

        quantity, cost = calculate_container_totals(display)

        self.assertEqual(quantity, 22_508)
        self.assertAlmostEqual(cost, 32_811.04)

    def test_dtf_summary_combines_brands_and_materials(self):
        source = pd.DataFrame([
            {
                **container_row("DTF", "180g", "S", 72),
                "brand": "Haloo",
                "color": "黑",
            },
            {
                **container_row("DTF", "CVC", "S", 100),
                "brand": "临时进货",
                "color": "黑",
            },
        ])

        summary = build_container_inventory_summary(
            build_container_display(source)
        )

        self.assertEqual(len(summary), 1)
        self.assertEqual(summary.iloc[0]["S"], 172)
        self.assertEqual(summary.iloc[0]["总件数"], 172)

    def test_uv_summary_uses_models_instead_of_sizes(self):
        source = pd.DataFrame([
            container_row("UV", "铁牌", "1040", 20_000),
            container_row("UV", "铁牌", "2030", 40_000),
        ])

        summary = build_container_inventory_summary(
            build_container_display(source)
        )

        self.assertEqual(summary.iloc[0]["1040"], 20_000)
        self.assertEqual(summary.iloc[0]["2030"], 40_000)
        self.assertEqual(summary.iloc[0]["总件数"], 60_000)
        self.assertNotIn("S", summary.columns)


if __name__ == "__main__":
    unittest.main()
