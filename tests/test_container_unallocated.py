import unittest

import pandas as pd

from db.inventory.container.unallocated import (
    attach_unallocated_cup_cargo,
    build_unallocated_cup_cargo,
)


class ContainerUnallocatedCargoTests(unittest.TestCase):
    def test_cases_attach_to_real_cup_skus_without_creating_fake_row(self):
        rows = pd.DataFrame([
            _row("第十四柜", "TRHU5477320", "2026-08-17", 351),
            _row("朱总第十五柜", "WHSU6109931", "2026-09-12", 49),
        ])

        cargo = build_unallocated_cup_cargo(rows)
        forecast = pd.DataFrame([
            {"品类": "保温杯", "规格": "直杯", "当前库存": 5000,
             "系统日均": 44},
            {"品类": "保温杯", "规格": "咖啡杯", "当前库存": 5000,
             "系统日均": 20},
        ])
        result = attach_unallocated_cup_cargo(forecast, cargo)

        self.assertEqual(len(result), 2)
        self.assertEqual(result["规格"].tolist(), ["直杯", "咖啡杯"])
        self.assertEqual(result["当前库存"].tolist(), [5000, 5000])
        self.assertEqual(result["系统日均"].tolist(), [44, 20])
        self.assertIn("第十四柜｜柜号 TRHU5477320 351箱", result.iloc[0]["待确认到货安排"])
        self.assertIn("朱总第十五柜｜柜号 WHSU6109931 49箱", result.iloc[0]["待确认到货安排"])

    def test_duplicate_sku_notes_do_not_duplicate_cases(self):
        row = _row("第十四柜", "TRHU5477320", "2026-08-17", 351)
        cargo = build_unallocated_cup_cargo(pd.DataFrame([row, row]))

        self.assertEqual(cargo["箱数"].tolist(), [351])


def _row(key, number, expected, cases):
    return {
        "container_key": key,
        "container_no": number,
        "expected_arrival_date": expected,
        "status": "在途",
        "note": f"待分配货物：保温杯{cases}箱｜直杯/咖啡杯箱数待确认",
    }


if __name__ == "__main__":
    unittest.main()
