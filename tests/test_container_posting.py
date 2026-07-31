import unittest
from unittest.mock import patch

from db.inventory.container.workflow.posting import post_container_inventory


class _Response:
    def __init__(self, data=None):
        self.data = data or []


class _Table:
    def __init__(self, client, name):
        self.client = client
        self.name = name
        self.result = []

    def update(self, values):
        self.client.updates.append((self.name, values))
        return self

    def insert(self, values):
        self.client.inserts.append((self.name, values))
        self.result = values if isinstance(values, list) else [values]
        return self

    def eq(self, *_args):
        return self

    def execute(self):
        return _Response(self.result)


class _Supabase:
    def __init__(self):
        self.updates = []
        self.inserts = []

    def table(self, name):
        return _Table(self, name)


def _item(status):
    return {
        "container_no": "TEST-1", "status": status,
        "department": "DTF", "category": "黑白短袖",
        "brand": "加州", "material": "160g", "color": "白",
        "size": "L", "quantity": 100, "unit_cost": 1.88,
        "actual_arrival_date": None, "actual_arrival_at": None,
    }


class ContainerPostingTests(unittest.TestCase):
    @patch("db.inventory.container.workflow.posting._apply_inventory_groups")
    @patch("db.inventory.container.workflow.posting._ensure_not_posted")
    @patch("db.inventory.container.workflow.posting._load_container_rows")
    def test_direct_post_records_arrival_then_posting(
        self, load_rows, _ensure, _apply
    ):
        load_rows.return_value = [_item("在途")]
        client = _Supabase()

        events = post_container_inventory(client, "TEST-1", "Andy")

        self.assertEqual([event["event_type"] for event in events], ["到柜", "入库"])
        self.assertEqual(events[0]["new_status"], "已到柜")
        self.assertEqual(events[1]["previous_status"], "已到柜")
        update = client.updates[0][1]
        self.assertEqual(update["status"], "已入库")
        self.assertIsNotNone(update["actual_arrival_date"])

    @patch("db.inventory.container.workflow.posting._apply_inventory_groups")
    @patch("db.inventory.container.workflow.posting._ensure_not_posted")
    @patch("db.inventory.container.workflow.posting._load_container_rows")
    def test_arrived_container_only_records_posting(
        self, load_rows, _ensure, _apply
    ):
        load_rows.return_value = [_item("已到柜")]
        client = _Supabase()

        events = post_container_inventory(client, "TEST-1", "Andy")

        self.assertEqual([event["event_type"] for event in events], ["入库"])
        self.assertEqual(events[0]["previous_status"], "已到柜")
        self.assertEqual(client.updates[0][1], {"status": "已入库"})


if __name__ == "__main__":
    unittest.main()
