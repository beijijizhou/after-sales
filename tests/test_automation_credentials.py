import unittest
from unittest.mock import Mock
from base64 import urlsafe_b64encode
import hashlib

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from db.automation_credentials import (
    CredentialDecryptionError,
    CredentialExpiredError,
    load_erp_token,
    save_erp_token,
)


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.payload = None

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def upsert(self, payload, **_kwargs):
        self.payload = payload
        return self

    def execute(self):
        return _Response(self.rows or ([self.payload] if self.payload else []))


class AutomationCredentialTests(unittest.TestCase):
    def test_token_is_encrypted_before_database_upsert(self):
        query = _Query()
        database = Mock()
        database.table.return_value = query

        save_erp_token(database, "Haloo", "plain-token", "secret")

        self.assertNotIn("plain-token", query.payload["encrypted_token"])
        self.assertEqual(query.payload["status"], "active")

    def test_database_token_round_trip(self):
        writer = _Query()
        database = Mock()
        database.table.return_value = writer
        save_erp_token(database, "Haloo", "plain-token", "secret")

        reader = _Query([writer.payload])
        database.table.return_value = reader
        token = load_erp_token(database, "Haloo", "secret")

        self.assertEqual(token, "plain-token")

    def test_database_token_reads_edge_function_encryption(self):
        secret = "secret"
        key = hashlib.sha256(
            f"after-sales:erp-api-token:{secret}".encode("utf-8")
        ).digest()
        nonce = b"123456789012"
        ciphertext = AESGCM(key).encrypt(
            nonce,
            b"edge-token",
            None,
        )
        encrypted_token = (
            "aesgcm:v1:"
            f"{_base64url(nonce)}:"
            f"{_base64url(ciphertext)}"
        )
        database = Mock()
        database.table.return_value = _Query([{
            "platform": "Haloo",
            "encrypted_token": encrypted_token,
            "status": "active",
        }])

        token = load_erp_token(database, "Haloo", secret)

        self.assertEqual(token, "edge-token")

    def test_wrong_deployment_secret_does_not_return_garbage(self):
        writer = _Query()
        database = Mock()
        database.table.return_value = writer
        save_erp_token(database, "Haloo", "plain-token", "secret")
        database.table.return_value = _Query([writer.payload])

        with self.assertRaises(CredentialDecryptionError):
            load_erp_token(database, "Haloo", "different-secret")

    def test_expired_database_token_does_not_fall_back_silently(self):
        database = Mock()
        database.table.return_value = _Query([{
            "platform": "Haloo",
            "encrypted_token": "unused",
            "status": "expired",
        }])

        with self.assertRaises(CredentialExpiredError):
            load_erp_token(database, "Haloo", "secret")


def _base64url(value):
    return (
        urlsafe_b64encode(value)
        .decode("utf-8")
        .rstrip("=")
    )


if __name__ == "__main__":
    unittest.main()
