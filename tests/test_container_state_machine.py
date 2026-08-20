import unittest

from db.inventory.container.tables import CONTAINER_STATUSES
from db.inventory.container.workflow.state import (
    STATE_ARRIVED,
    STATE_IN_TRANSIT,
    STATE_POSTED,
    normalize_container_state,
    validate_container_transition,
)
from ui.inventory.container.today import container_tab_names


class ContainerStateMachineTests(unittest.TestCase):
    def test_new_containers_only_allow_transit_or_cancel(self):
        self.assertEqual(CONTAINER_STATUSES, ["在途", "取消"])

    def test_pending_inventory_is_first_tab(self):
        names = container_tab_names(
            has_today_arrivals=True,
            has_pending_posting=True,
        )

        self.assertEqual(names[0], "待确认入库")
        self.assertEqual(names[1], "今日到柜")

    def test_empty_pending_inventory_moves_tab_to_end(self):
        names = container_tab_names(
            has_today_arrivals=False,
            has_pending_posting=False,
        )

        self.assertEqual(names[-1], "待确认入库")
        self.assertIn("在途货柜", names)

    def test_container_search_and_edit_is_a_standalone_tab(self):
        names = container_tab_names(
            has_today_arrivals=False,
            has_pending_posting=False,
        )

        self.assertIn("查找与修改货柜", names)
        self.assertEqual(names.count("查找与修改货柜"), 1)

    def test_legacy_statuses_are_normalized_in_code(self):
        self.assertEqual(
            normalize_container_state("未到货"), STATE_IN_TRANSIT
        )
        self.assertEqual(
            normalize_container_state("已到货"), STATE_ARRIVED
        )

    def test_valid_flow_is_transit_arrived_posted(self):
        self.assertEqual(
            validate_container_transition(STATE_IN_TRANSIT, STATE_ARRIVED),
            STATE_IN_TRANSIT,
        )
        self.assertEqual(
            validate_container_transition(STATE_ARRIVED, STATE_POSTED),
            STATE_ARRIVED,
        )

    def test_direct_ui_action_still_uses_full_state_path(self):
        self.assertEqual(
            validate_container_transition(STATE_IN_TRANSIT, STATE_ARRIVED),
            STATE_IN_TRANSIT,
        )
        self.assertEqual(
            validate_container_transition(STATE_ARRIVED, STATE_POSTED),
            STATE_ARRIVED,
        )
        with self.assertRaises(ValueError):
            validate_container_transition(STATE_IN_TRANSIT, STATE_POSTED)


if __name__ == "__main__":
    unittest.main()
