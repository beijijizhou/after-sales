import unittest
from pathlib import Path

import pandas as pd

from db.consumables.planning import build_consumable_forecast_usage
from db.inventory.planning.incoming import normalize_forecast_usage
from db.inventory.planning.uv_consumption import build_uv_forecast_usage
from db.planning import USAGE_VALUE_COLUMNS, build_daily_usage_contract
from utils.erp.inventory_mapping import KEY_COLUMNS


class InventoryPlanningUsageContractTests(unittest.TestCase):
    def test_duplicate_source_rows_are_aggregated_at_planning_boundary(self):
        result = build_daily_usage_contract(
            pd.DataFrame([
                {"sku": "A", "rate": 2, "days": 3, "total": 6},
                {"sku": "A", "rate": 4, "days": 5, "total": 20},
            ]),
            key_columns=["sku"],
            daily_usage_column="rate",
            effective_days_column="days",
            total_usage_column="total",
            source_type="test",
            source_label="测试来源",
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["daily_usage"], 6)
        self.assertEqual(result.iloc[0]["effective_days"], 5)
        self.assertEqual(result.iloc[0]["total_usage"], 26)

    def test_apparel_and_uv_adapters_share_the_same_contract(self):
        apparel = normalize_forecast_usage(
            pd.DataFrame([{
                "color": "白", "size": "L", "consumption_quantity": 12,
            }]),
            "DTF",
            "彩色短袖",
        )
        uv = build_uv_forecast_usage(pd.DataFrame([{
            "品类": "铁板画", "材质": "铁牌", "颜色": "白",
            "型号": "2030", "每日消耗": 12, "有效数据天数": 7,
            "自然日均消耗": 6, "窗口总消耗": 84, "窗口天数": 14,
        }]))

        expected = [*KEY_COLUMNS, *USAGE_VALUE_COLUMNS]
        self.assertEqual(apparel.columns.tolist(), expected)
        self.assertEqual(uv.columns.tolist(), expected)
        self.assertEqual(apparel.iloc[0]["daily_usage"], 12)
        self.assertEqual(uv.iloc[0]["daily_usage"], 12)

    def test_consumables_use_the_same_evidence_fields(self):
        result = build_consumable_forecast_usage(pd.DataFrame([{
            "item_id": "ink", "最近领用日均": 8,
            "有效数据天数": 4, "窗口天数": 14, "总领用量": 32,
        }]))

        self.assertEqual(
            result.columns.tolist(), ["item_id", *USAGE_VALUE_COLUMNS]
        )
        self.assertEqual(result.iloc[0]["usage_source_type"], "warehouse_issue")
        self.assertEqual(result.iloc[0]["effective_days"], 4)

    def test_active_planning_adapters_cannot_restore_uv_side_calculation(self):
        root = Path(__file__).resolve().parents[1]
        uv_model = (root / "db/inventory/planning/uv_consumption.py").read_text()
        uv_view = (root / "ui/inventory/planning/uv_view.py").read_text()
        self.assertNotIn("def build_uv_container_coverage", uv_model)
        self.assertNotIn("build_uv_container_coverage", uv_view)
        for relative in [
            "db/inventory/planning/incoming.py",
            "db/inventory/planning/uv_consumption.py",
            "db/consumables/planning.py",
            "automation/sync/colored_models.py",
        ]:
            self.assertIn(
                "build_daily_usage_contract", (root / relative).read_text()
            )


if __name__ == "__main__":
    unittest.main()
