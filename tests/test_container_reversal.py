import unittest
from unittest.mock import ANY, patch

import pandas as pd

from db.inventory.container.workflow.reversal import (
    extract_inventory_batch_id,
    get_container_undo_kind,
    undo_latest_container_confirmation,
)


class _Response:
    data = []


class _Rpc:
    def __init__(self, client, name, parameters):
        self.client = client
        self.name = name
        self.parameters = parameters

    def execute(self):
        self.client.calls.append((self.name, self.parameters))
        return _Response()


class _Supabase:
    def __init__(self):
        self.calls = []

    def rpc(self, name, parameters):
        return _Rpc(self, name, parameters)


class ContainerReversalTests(unittest.TestCase):
    def test_inventory_batch_resolves_back_to_posted_container(self):
        from ui.inventory.history.workflows import reversal as history_ui

        selected = pd.DataFrame([{
            "batch_id": "inventory-batch-1", "quantity_change": 100,
            "reason": "货柜入库：HAMU4767628",
        }])
        target = pd.DataFrame([{
            "container_key": "11柜", "status": "已入库",
        }])
        with patch.object(
            history_ui, "load_posted_container_by_inventory_batch",
            return_value=target,
        ) as loader:
            result = history_ui.load_container_batch_target(
                object(), selected
            )

        loader.assert_called_once_with(ANY, "inventory-batch-1")
        self.assertEqual(result.iloc[0]["container_key"], "11柜")

    def test_posted_container_batch_uses_container_aware_correction(self):
        from ui.inventory.history.workflows import reversal as history_ui

        target = pd.DataFrame([{
            "container_key": "11柜", "status": "已入库",
        }])
        with (
            patch.object(history_ui, "st") as streamlit,
            patch.object(history_ui, "has_permission", return_value=True),
            patch.object(
                history_ui, "render_posted_container_correction"
            ) as correction,
            patch.object(history_ui, "render_container_undo_action") as undo,
        ):
            streamlit.segmented_control.return_value = "修改数量与成本"
            history_ui.render_container_batch_management(
                object(), target, "test"
            )

        correction.assert_called_once()
        pd.testing.assert_frame_equal(correction.call_args.args[1], target)
        self.assertEqual(correction.call_args.args[2], "11柜")
        undo.assert_not_called()

    def test_container_batch_never_uses_generic_inventory_undo(self):
        from ui.inventory.history.workflows import reversal as history_ui

        movements = pd.DataFrame([{
            "batch_key": "movement|inventory-batch-1",
            "batch_id": "inventory-batch-1",
            "quantity_change": 100,
            "reason": "货柜入库：HAMU4767628",
        }])
        target = pd.DataFrame([{
            "container_key": "11柜", "status": "已入库",
        }])
        with (
            patch.object(
                history_ui, "add_movement_batch_key",
                return_value=movements,
            ),
            patch.object(history_ui, "render_movement_table"),
            patch.object(
                history_ui, "load_container_batch_target",
                return_value=target,
            ),
            patch.object(
                history_ui, "render_container_batch_management"
            ) as container_management,
            patch.object(history_ui, "render_movement_undo") as generic_undo,
        ):
            history_ui.render_selected_movement(
                object(), movements, "movement|inventory-batch-1",
                allow_undo=True,
            )

        container_management.assert_called_once()
        generic_undo.assert_not_called()

    def test_posting_review_is_rendered_inside_the_undo_panel(self):
        from ui.inventory.container import reversal as reversal_ui

        events = []

        class _Panel:
            def __enter__(self):
                events.append("panel_enter")

            def __exit__(self, *_args):
                events.append("panel_exit")

        target = pd.DataFrame([{
            "container_key": "11柜", "container_no": "HAMU4767628",
            "status": "已入库", "department": "UV",
            "category": "铁板画",
        }])
        with (
            patch.object(reversal_ui, "has_permission", return_value=True),
            patch.object(reversal_ui.st, "expander", return_value=_Panel()),
            patch.object(
                reversal_ui, "render_container_inventory_change_review",
                side_effect=lambda *_args: events.append("stock_review"),
            ),
            patch.object(
                reversal_ui, "_render_undo_controls",
                side_effect=lambda *_args: events.append("undo_controls"),
            ),
        ):
            reversal_ui.render_container_undo_action(
                object(), target, "11柜", "test"
            )

        self.assertEqual(events, [
            "panel_enter", "stock_review", "undo_controls", "panel_exit",
        ])

    def test_extracts_inventory_batch_from_event_note(self):
        batch_id = "09c429e7-9591-49a1-9622-27e1603e5116"
        self.assertEqual(
            extract_inventory_batch_id(f"已入库｜库存批次：{batch_id}"),
            batch_id,
        )

    def test_undo_kind_follows_current_state(self):
        self.assertEqual(get_container_undo_kind("已入库"), "posting")
        self.assertEqual(get_container_undo_kind("已到柜"), "arrival")
        self.assertIsNone(get_container_undo_kind("在途"))

    @patch("db.inventory.container.workflow.reversal._insert_event")
    @patch("db.inventory.container.workflow.reversal._update_container")
    @patch("db.inventory.container.workflow.reversal._load_latest_event")
    @patch("db.inventory.container.workflow.reversal._load_current_container")
    def test_undo_arrival_restores_previous_state_and_clears_actual_date(
        self, load_current, load_event, update, insert,
    ):
        load_current.return_value = {
            "container_no": "11柜", "status": "已到柜",
            "actual_arrival_date": "2026-08-05",
            "actual_arrival_at": None,
        }
        load_event.return_value = {
            "previous_status": "在途", "note": "",
        }
        client = object()

        result = undo_latest_container_confirmation(
            client, "11柜", "Andy", "误点"
        )

        update.assert_called_once_with(client, "11柜", ANY)
        values = update.call_args.args[2]
        self.assertEqual(values["status"], "在途")
        self.assertIsNone(values["actual_arrival_date"])
        self.assertEqual(insert.call_args.args[1]["event_type"], "撤销到柜")
        self.assertEqual(result["status"], "在途")

    @patch("db.inventory.container.workflow.reversal._insert_event")
    @patch("db.inventory.container.workflow.reversal._update_container")
    @patch("db.inventory.container.workflow.reversal._load_latest_event")
    @patch("db.inventory.container.workflow.reversal._load_current_container")
    @patch("db.inventory.container.workflow.reversal.reverse_batch")
    def test_undo_posting_reverses_linked_inventory_batch(
        self, reverse, load_current, load_event, update, insert,
    ):
        batch_id = "11111111-2222-3333-4444-555555555555"
        load_current.return_value = {
            "container_no": "11柜", "status": "已入库",
            "actual_arrival_date": "2026-08-05",
            "actual_arrival_at": None,
            "department": "DTF", "category": "黑白短袖",
        }
        load_event.return_value = {
            "previous_status": "已到柜",
            "note": f"库存批次：{batch_id}",
        }
        client = _Supabase()

        result = undo_latest_container_confirmation(
            client, "11柜", "Andy"
        )

        update.assert_called_once_with(client, "11柜", {"status": "已到柜"})
        reference = reverse.call_args.args[1]
        self.assertEqual(reference.batch_id, batch_id)
        self.assertEqual(reference.department, "DTF")
        self.assertEqual(reference.category, "黑白短袖")
        self.assertEqual(reverse.call_args.args[2], "Andy")
        self.assertEqual(insert.call_args.args[1]["event_type"], "撤销入库")
        self.assertEqual(result["batch_id"], batch_id)


if __name__ == "__main__":
    unittest.main()
