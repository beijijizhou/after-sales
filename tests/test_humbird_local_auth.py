from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from automation.api.humbird import local_auth
from automation.api.humbird.config import load_humbird_credentials


class HumbirdLocalAuthTest(unittest.TestCase):
    @patch(
        "automation.api.humbird.config._load_legacy_credentials",
        return_value=None,
    )
    def test_longfeng_uses_its_platform_open_api_key(self, _legacy):
        credentials = load_humbird_credentials(
            {
                "HUMBIRD_OPEN_API_KEY": "haloo-only",
                "humbird_open_api": {
                    "隆丰": {"api_key": "longfeng-key"},
                },
            },
            "隆丰",
        )

        self.assertEqual(credentials["api_key"], "longfeng-key")
        self.assertEqual(
            credentials["credential_source"], "humbird_open_api"
        )

    @patch(
        "automation.api.humbird.config._load_legacy_credentials",
        side_effect=RuntimeError("expired legacy token"),
    )
    def test_open_api_key_is_not_blocked_by_expired_legacy_token(
        self, _legacy
    ):
        credentials = load_humbird_credentials(
            {
                "humbird_open_api": {
                    "隆丰": {"api_key": "longfeng-key"},
                },
            },
            "隆丰",
        )

        self.assertEqual(credentials["api_key"], "longfeng-key")

    @patch(
        "automation.api.humbird.config._load_legacy_credentials",
        return_value=None,
    )
    def test_global_open_api_key_remains_haloo_only(self, _legacy):
        with self.assertRaisesRegex(ValueError, "隆丰"):
            load_humbird_credentials(
                {"HUMBIRD_OPEN_API_KEY": "haloo-only"},
                "隆丰",
            )

    @patch("automation.api.humbird.config.load_erp_token")
    def test_haloo_keeps_open_api_key_and_database_token(self, load):
        load.return_value = "database-token"
        credentials = load_humbird_credentials(
            {
                "HUMBIRD_OPEN_API_KEY": "official-key",
                "SUPABASE_KEY": "service-key",
            },
            "Haloo",
            supabase=object(),
        )

        self.assertEqual(credentials["api_key"], "official-key")
        self.assertEqual(credentials["token"], "database-token")
        self.assertEqual(
            credentials["credential_source"], "humbird_open_api"
        )
        self.assertEqual(
            credentials["fallback_credential_source"], "database"
        )
        load.assert_called_once()

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
