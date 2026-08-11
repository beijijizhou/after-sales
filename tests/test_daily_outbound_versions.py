from datetime import date
import unittest
from unittest.mock import Mock

import pandas as pd

from db.inventory.operations.daily_outbound_versions import (
    build_daily_outbound_edit_rows,
    save_daily_outbound_revision,
)
from db.inventory.planning.demand_anomaly import (
    _versioned_daily_outbound_history,
)


class DailyOutboundVersionTests(unittest.TestCase):
    def test_edit_rows_use_declared_quantity_not_applied_quantity(self):
        result = build_daily_outbound_edit_rows({
            "inventory_daily_outbound_batches": {
                "movement_date": "2026-08-10",
            },
            "inventory_daily_outbound_lines": [{
                "brand": "B64", "material": "160g", "color": "白",
                "size": "3XL", "requested_quantity": 2520,
                "applied_quantity": 0, "shortage_quantity": 2520,
            }],
        })

        self.assertEqual(result.iloc[0]["数量"], 2520)

    def test_save_sends_declared_quantities_without_temporary_inbound(self):
        supabase = Mock()
        supabase.rpc.return_value.execute.return_value.data = {
            "requested_total": 2520,
            "applied_total": 0,
            "shortage_total": 2520,
        }
        rows = pd.DataFrame([{
            "品牌": "B64", "材质": "160g", "颜色": "白",
            "尺码": "3XL", "数量": 2520,
        }])

        result = save_daily_outbound_revision(
            supabase, "DTF", "黑白短袖", date(2026, 8, 10),
            rows, "Andy",
        )

        parameters = supabase.rpc.call_args.args[1]
        self.assertEqual(parameters["p_rows"][0]["requested_quantity"], 2520)
        self.assertEqual(result["applied_total"], 0)
        self.assertEqual(result["shortage_total"], 2520)

    def test_consumption_model_uses_declared_not_applied_quantity(self):
        database = Mock()
        with unittest.mock.patch(
            "db.inventory.planning.demand_anomaly.load_daily_outbound_revisions",
            return_value=[{
                "movement_date": "2026-08-10",
                "current_revision": 2,
                "inventory_daily_outbound_revisions": [{
                    "revision_number": 2,
                    "inventory_daily_outbound_lines": [{
                        "color": "白", "size": "3XL",
                        "requested_quantity": 2520,
                        "applied_quantity": 0,
                        "shortage_quantity": 2520,
                    }],
                }],
            }],
        ):
            result = _versioned_daily_outbound_history(
                database, "DTF", "黑白短袖",
                date(2026, 8, 10), date(2026, 8, 10),
            )

        self.assertEqual(result.iloc[0]["实际出库"], 2520)
