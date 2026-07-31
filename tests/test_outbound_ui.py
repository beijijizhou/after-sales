import unittest

from ui.inventory.operations.outbound import outbound_specs_signature


class OutboundUiTests(unittest.TestCase):
    def test_new_container_spec_changes_editor_signature(self):
        original = {
            "160g/Caribbean/Box/70件": (
                "Caribbean", "160g", "Box", 70
            )
        }
        expanded = {
            **original,
            "160g/Caribbean/Box/72件": (
                "Caribbean", "160g", "Box", 72
            ),
        }

        self.assertNotEqual(
            outbound_specs_signature(original),
            outbound_specs_signature(expanded),
        )


if __name__ == "__main__":
    unittest.main()
