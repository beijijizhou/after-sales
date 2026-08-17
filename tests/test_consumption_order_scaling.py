import unittest

import pandas as pd

from db.inventory.planning.consumption import scale_consumption_model
from ui.inventory.planning.comparison import _model_order_quantity


class ConsumptionOrderScalingTests(unittest.TestCase):
    def test_18000_orders_scale_15000_baseline(self):
        source = pd.DataFrame([{
            "order_quantity": 15000,
            "consumption_quantity": 1000,
            "color": "黑",
            "size": "L",
        }])
        result = scale_consumption_model(source, 18000)
        self.assertEqual(result.iloc[0]["order_quantity"], 18000)
        self.assertEqual(result.iloc[0]["consumption_quantity"], 1200)
        self.assertEqual(_model_order_quantity(result), 18000)


if __name__ == "__main__":
    unittest.main()
