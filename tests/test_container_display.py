import unittest
from datetime import date

import pandas as pd

from db.inventory.container.tables import build_container_display


def container_row(department, material, item, quantity):
    return {
        "container_key": "9柜",
        "shipped_date": date(2026, 6, 5),
        "expected_arrival_date": date(2026, 7, 20),
        "actual_arrival_date": date(2026, 7, 28),
        "actual_arrival_at": "2026-07-28T15:30:00-04:00",
        "container_no": "9柜",
        "department": department,
        "category": "牌类" if department == "UV" else "黑白短袖",
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


if __name__ == "__main__":
    unittest.main()
