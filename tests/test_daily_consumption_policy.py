import unittest

from utils.daily_consumption import (
    ENTRY_MANUAL,
    ENTRY_SYSTEM,
    daily_consumption_source,
    inventory_daily_consumption_flow,
    is_daily_consumption_reason,
)


class DailyConsumptionPolicyTests(unittest.TestCase):
    def test_inventory_flows_keep_only_input_and_model_source_different(self):
        black_white = inventory_daily_consumption_flow(
            "DTF", "黑白短袖"
        )
        colored = inventory_daily_consumption_flow("DTF", "彩色短袖")
        uv = inventory_daily_consumption_flow("UV", "铁板画")

        self.assertEqual(black_white.entry_source, ENTRY_MANUAL)
        self.assertEqual(colored.entry_source, ENTRY_SYSTEM)
        self.assertEqual(uv.entry_source, ENTRY_SYSTEM)
        self.assertEqual(colored.ledger, black_white.ledger)
        self.assertEqual(uv.ledger, black_white.ledger)

    def test_all_inventory_daily_reasons_share_one_classification(self):
        reasons = [
            "仓库每日出货",
            "每日正常出货",
            "彩色短袖生产自动扣减 2026-08-03",
            "Google Sheets UV每日消耗｜2026-08-03｜Tie_2030",
        ]
        self.assertTrue(all(map(is_daily_consumption_reason, reasons)))
        self.assertEqual(daily_consumption_source(reasons[0]), ENTRY_MANUAL)
        self.assertEqual(daily_consumption_source(reasons[-1]), ENTRY_SYSTEM)

    def test_temporary_adjustment_is_not_daily_consumption(self):
        self.assertFalse(is_daily_consumption_reason("临时库存调整"))


if __name__ == "__main__":
    unittest.main()
