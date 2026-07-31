import unittest

from ui.consumables.operations.stock_tables import (
    build_daily_issue_template,
)


class ConsumableDailyBoxTests(unittest.TestCase):
    def test_template_displays_and_accepts_box_counts(self):
        items = {
            "墨水｜白色墨水｜瓶": {
                "current_quantity": 100,
                "units_per_package": 20,
            }
        }

        result = build_daily_issue_template(items)

        self.assertEqual(result.loc[0, "当前库存（箱）"], 5)
        self.assertEqual(result.loc[0, "每箱数量"], 20)
        self.assertEqual(result.loc[0, "今日领用（箱）"], 0)


if __name__ == "__main__":
    unittest.main()
