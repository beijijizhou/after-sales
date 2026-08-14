import unittest

from ui.inventory.container.selection import (
    container_selection_widget_key,
    selected_container_key,
)


class ContainerSelectionTests(unittest.TestCase):
    def test_widget_key_changes_after_confirmed_container_disappears(self):
        state = {}
        first_key = container_selection_widget_key(
            state, "transit", ["container-a", "container-b"]
        )
        same_key = container_selection_widget_key(
            state, "transit", ["container-a", "container-b"]
        )
        next_key = container_selection_widget_key(
            state, "transit", ["container-b"]
        )

        self.assertEqual(first_key, same_key)
        self.assertNotEqual(first_key, next_key)

    def test_stale_row_position_is_ignored_instead_of_indexing(self):
        self.assertIsNone(selected_container_key(["container-b"], [1]))

    def test_current_row_position_resolves_container_key(self):
        self.assertEqual(
            selected_container_key(["container-a", "container-b"], [1]),
            "container-b",
        )


if __name__ == "__main__":
    unittest.main()
