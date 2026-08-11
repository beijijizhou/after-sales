import unittest

from ui.inventory.history.daily_outbound_revisions import _flatten_revisions


class DailyOutboundRevisionHistoryTests(unittest.TestCase):
    def test_marks_only_current_revision_active(self):
        summaries, details = _flatten_revisions([{
            "id": "daily-1",
            "movement_date": "2026-08-10",
            "current_revision": 2,
            "inventory_daily_outbound_revisions": [
                {
                    "revision_number": 1, "action": "create",
                    "requested_total": 7834, "applied_total": 5194,
                    "shortage_total": 2640, "created_by": "Andy",
                    "created_at": "2026-08-10T20:00:00Z",
                    "inventory_daily_outbound_lines": [],
                },
                {
                    "revision_number": 2, "action": "edit",
                    "requested_total": 54150, "applied_total": 36230,
                    "shortage_total": 17920, "created_by": "Andy",
                    "created_at": "2026-08-10T21:00:00Z",
                    "inventory_daily_outbound_lines": [{
                        "brand": "Caribbean", "material": "160g",
                        "color": "白", "size": "L",
                        "requested_quantity": 20360,
                        "applied_quantity": 18224,
                        "shortage_quantity": 2136,
                    }],
                },
            ],
        }])

        states = {row["版本"]: row["状态"] for row in summaries}
        self.assertEqual(states, {1: "历史版本", 2: "当前有效"})
        self.assertEqual(details["daily-1|2"][0]["未扣差额"], 2136)


if __name__ == "__main__":
    unittest.main()
