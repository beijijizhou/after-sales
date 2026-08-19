import unittest
from unittest.mock import patch

from automation.sync.credentials import load_platform_credentials


class ProductionCredentialTests(unittest.TestCase):
    def test_s2b_uses_requested_department_account(self):
        with patch(
            "automation.sync.credentials.load_s2b_account",
            return_value={"token": "uv-token"},
        ) as loader:
            credentials = load_platform_credentials(
                "S2B", {}, department="UV"
            )

        self.assertEqual(credentials, {"token": "uv-token"})
        loader.assert_called_once_with({}, "UV")


if __name__ == "__main__":
    unittest.main()
