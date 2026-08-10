from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from automation.api.humbird import local_auth
from automation.api.humbird.config import load_humbird_credentials


class HumbirdLocalAuthTest(unittest.TestCase):
    @patch(
        "automation.api.humbird.config.load_erp_token",
        return_value="database-token",
    )
    def test_database_token_has_priority_over_local_and_secrets(self, load):
        database = object()
        credentials = load_humbird_credentials(
            {
                "SUPABASE_KEY": "service-key",
                "factory_credentials": {
                    "Haloo": {"token": "secrets-token"},
                },
            },
            "Haloo",
            supabase=database,
        )

        self.assertEqual(credentials["token"], "database-token")
        self.assertEqual(credentials["credential_source"], "database")
        self.assertIs(credentials["credential_store"], database)
        load.assert_called_once_with(database, "Haloo", "service-key")

    def test_save_token_preserves_other_profiles_without_printing_token(self):
        with TemporaryDirectory() as directory:
            target = Path(directory) / "credentials.toml"
            target.write_text(
                '[factory_credentials."Haloo"]\nold = "kept"\n\n'
                '[factory_credentials."莆田"]\ntoken = "putian-token"\n',
                encoding="utf-8",
            )
            with patch.object(local_auth, "LOCAL_CREDENTIALS", target):
                local_auth._save_token("Haloo", "haloo-token")
                profiles = local_auth._read_profiles()

            self.assertEqual(profiles["Haloo"]["old"], "kept")
            self.assertEqual(profiles["Haloo"]["token"], "haloo-token")
            self.assertEqual(profiles["莆田"]["token"], "putian-token")
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
