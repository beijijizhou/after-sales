import unittest

from ui.inventory.container.today import container_tab_names


class ContainerTabTests(unittest.TestCase):
    def test_today_arrivals_are_first_when_present(self):
        self.assertEqual(
            container_tab_names(True)[0],
            "今日到货",
        )

    def test_today_arrivals_are_last_when_empty(self):
        self.assertEqual(
            container_tab_names(False)[-1],
            "今日到货",
        )


if __name__ == "__main__":
    unittest.main()
