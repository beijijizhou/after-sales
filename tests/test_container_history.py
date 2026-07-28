import unittest

import pandas as pd

from db.inventory.container.history import build_container_history_display


class ContainerHistoryTests(unittest.TestCase):
    def test_actual_and_confirmation_times_use_new_york_time(self):
        source = pd.DataFrame([{
            "container_key": "9柜",
            "container_no": "9柜",
            "event_type": "到货",
            "effective_date": "2026-07-28",
            "actual_arrival_at": "2026-07-28T19:30:00+00:00",
            "previous_status": "未到货",
            "new_status": "已到货",
            "operated_by": "Andy",
            "note": "",
            "created_at": "2026-07-28T19:35:00+00:00",
        }])

        display = build_container_history_display(source)

        self.assertEqual(
            display.loc[0, "实际到货时间（纽约）"],
            "2026-07-28 15:30:00",
        )
        self.assertEqual(
            display.loc[0, "确认时间（纽约）"],
            "2026-07-28 15:35:00",
        )


if __name__ == "__main__":
    unittest.main()
