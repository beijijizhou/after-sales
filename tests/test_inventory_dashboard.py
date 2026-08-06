from datetime import date
import unittest

import pandas as pd

from automation.sync.daily_inventory_consumption import (
    AUTOMATIC_DAILY_FLOWS,
)
from db.inventory.dashboard import (
    build_automatic_missing_dates,
    build_daily_completion_dates,
    build_daily_completion_table,
)


class InventoryDashboardTests(unittest.TestCase):
    def test_daily_completion_separates_four_flows(self):
        movements = pd.DataFrame([
            {
                "department": "DTF", "category": "黑白短袖",
                "movement_date": "2026-08-03", "quantity_change": -100,
                "reason": "仓库每日出货", "batch_id": "bw",
                "reversal_of_batch_id": None,
            },
            {
                "department": "DTF", "category": "彩色短袖",
                "movement_date": "2026-08-04", "quantity_change": -50,
                "reason": "彩色短袖生产自动扣减 2026-08-04",
                "batch_id": "color", "reversal_of_batch_id": None,
            },
            {
                "department": "UV", "category": "铁板画",
                "movement_date": "2026-08-04", "quantity_change": -20,
                "reason": "Google Sheets UV每日消耗｜2026-08-04｜Tie_2030",
                "batch_id": "uv", "reversal_of_batch_id": None,
            },
        ])
        consumables = pd.DataFrame([{
            "id": "c1", "movement_type": "issue",
            "movement_date": "2026-08-02", "reversal_of_batch_id": None,
        }])

        result = build_daily_completion_dates(movements, consumables)

        self.assertEqual(result["black_white"], {date(2026, 8, 3)})
        self.assertEqual(result["colored"], {date(2026, 8, 4)})
        self.assertEqual(result["uv"], {date(2026, 8, 4)})
        self.assertEqual(result["consumables"], {date(2026, 8, 2)})

    def test_completion_table_lists_missing_dates_and_action(self):
        completed = {
            "black_white": {date(2026, 8, 3)},
            "consumables": {date(2026, 8, 4)},
            "colored": {date(2026, 8, 3), date(2026, 8, 4)},
            "uv": set(),
        }

        result = build_daily_completion_table(
            completed, date(2026, 8, 3), date(2026, 8, 4)
        ).set_index("出库项目")

        self.assertEqual(result.loc["黑白短袖", "待处理日期"], "08/04")
        self.assertEqual(result.loc["彩色短袖", "待处理天数"], 0)
        self.assertEqual(
            result.loc["UV 生产库存", "处理方式"], "读取来源并扣减"
        )

    def test_automatic_sources_are_registered_in_one_place(self):
        self.assertEqual(
            [flow.code for flow in AUTOMATIC_DAILY_FLOWS],
            ["colored", "uv"],
        )

    def test_automatic_date_options_only_include_missing_sources(self):
        completed = {
            "colored": {date(2026, 8, 3), date(2026, 8, 4)},
            "uv": {date(2026, 8, 4)},
        }

        result = build_automatic_missing_dates(
            completed, date(2026, 8, 3), date(2026, 8, 4)
        )

        self.assertEqual(
            result,
            {date(2026, 8, 3): "UV 生产库存"},
        )


if __name__ == "__main__":
    unittest.main()
