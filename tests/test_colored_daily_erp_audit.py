import unittest
from datetime import date

import pandas as pd

from ui.inventory.planning.colored_daily_audit import (
    build_colored_daily_erp_detail,
    build_colored_daily_erp_summary,
)


class ColoredDailyErpAuditTests(unittest.TestCase):
    def setUp(self):
        self.production = pd.DataFrame([
            {
                "business_date": "2026-08-15", "platform": "S2B",
                "color": "黄色", "size": "S", "quantity": 120,
                "record_count": 10,
            },
            {
                "business_date": "2026-08-15", "platform": "SDS2",
                "color": "黄色", "size": "L", "quantity": 80,
                "record_count": 6,
            },
        ])
        self.ledger = pd.DataFrame([
            {
                "日期": date(2026, 8, 15), "颜色": "黄色",
                "尺码": "S", "生产数量": 150,
            },
            {
                "日期": date(2026, 8, 14), "颜色": "绿色",
                "尺码": "M", "生产数量": 20,
            },
        ])

    def test_daily_summary_exposes_erp_quantity_platforms_and_difference(self):
        result = build_colored_daily_erp_summary(
            self.production, self.ledger,
            date(2026, 8, 14), date(2026, 8, 15),
        )

        saved = result[result["日期"].eq(date(2026, 8, 15))].iloc[0]
        missing = result[result["日期"].eq(date(2026, 8, 14))].iloc[0]
        self.assertEqual(saved["ERP生产件数"], 200)
        self.assertEqual(saved["库存已扣件数"], 150)
        self.assertEqual(saved["待核对差异"], 50)
        self.assertEqual(saved["平台数"], 2)
        self.assertEqual(saved["已读取平台"], "S2B、SDS2")
        self.assertEqual(saved["状态"], "已保存")
        self.assertEqual(missing["状态"], "缺少ERP日表")

    def test_selected_day_detail_is_wide_and_uses_business_size_order(self):
        result = build_colored_daily_erp_detail(
            self.production, date(2026, 8, 15)
        )

        self.assertEqual(
            result.columns.tolist(),
            [
                "平台", "颜色", "S", "M", "L", "XL", "2XL",
                "3XL", "4XL", "5XL", "其他尺码", "合计", "记录数",
            ],
        )
        self.assertEqual(int(result["合计"].sum()), 200)


if __name__ == "__main__":
    unittest.main()
