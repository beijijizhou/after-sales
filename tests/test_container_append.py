import unittest

from db.inventory.container.repository import _container_item_key


class ContainerAppendTests(unittest.TestCase):
    def test_item_identity_is_case_insensitive_and_uses_business_dimensions(self):
        left = {
            "department": "UV", "category": "拼图", "brand": "",
            "material": "拼图白胚", "color": "白", "size": "52X38",
            "quantity": 8000,
        }
        right = {
            **left, "department": "uv", "size": "52x38", "quantity": 1,
        }

        self.assertEqual(_container_item_key(left), _container_item_key(right))


if __name__ == "__main__":
    unittest.main()
