"""Encrypted shared credentials for server-side ERP automation."""

from base64 import urlsafe_b64encode
from base64 import urlsafe_b64decode
from datetime import datetime, timezone
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


TABLE = "erp_api_credentials"


class CredentialDecryptionError(RuntimeError):
    pass


class CredentialExpiredError(RuntimeError):
    pass


def load_erp_token(supabase, platform, encryption_secret):
    response = (
        supabase.table(TABLE)
        .select("platform,encrypted_token,status")
        .eq("platform", platform)
        .limit(1)
        .execute()
    )
    rows = list(response.data or [])
    if not rows:
        return None
    row = rows[0]
    if row.get("status") == "expired":
        raise CredentialExpiredError(
            f"{platform} 共享授权已失效，需要管理员重新登录并更新一次"
        )
    try:
        encrypted_token = str(row["encrypted_token"])
        if encrypted_token.startswith("aesgcm:v1:"):
            return _decrypt_aesgcm_token(encrypted_token, encryption_secret)

        return _cipher(encryption_secret).decrypt(
            encrypted_token.encode("utf-8")
        ).decode("utf-8")
    except (
        InvalidToken, KeyError, UnicodeDecodeError,
        ValueError,
    ) as error:
        raise CredentialDecryptionError(
            f"{platform} 数据库 token 无法解密；请确认部署密钥一致"
        ) from error


def save_erp_token(
    supabase,
    platform,
    token,
    encryption_secret,
    updated_by="system",
):
    now = _now()
    payload = {
        "platform": platform,
        "encrypted_token": _cipher(encryption_secret).encrypt(
            str(token).encode("utf-8")
        ).decode("utf-8"),
        "token_fingerprint": _fingerprint(token),
        "status": "active",
        "last_refreshed_at": now,
        "last_error": None,
        "updated_by": updated_by,
        "updated_at": now,
    }
    return (
        supabase.table(TABLE)
        .upsert(payload, on_conflict="platform")
        .execute()
        .data
    )


def mark_erp_token_used(supabase, platform):
    return (
        supabase.table(TABLE)
        .update({"last_used_at": _now(), "last_error": None})
        .eq("platform", platform)
        .execute()
        .data
    )


def mark_erp_token_error(supabase, platform, message, expired=False):
    values = {
        "status": "expired" if expired else "error",
        "last_error": str(message)[:1000],
        "updated_at": _now(),
    }
    return (
        supabase.table(TABLE)
        .update(values)
        .eq("platform", platform)
        .execute()
        .data
    )


def _cipher(secret):
    digest = hashlib.sha256(
        f"after-sales:erp-api-token:{secret}".encode("utf-8")
    ).digest()
    return Fernet(urlsafe_b64encode(digest))


def _decrypt_aesgcm_token(value, secret):
    _prefix, _version, nonce, ciphertext = value.split(":", 3)
    cipher = AESGCM(_encryption_key(secret))
    return cipher.decrypt(
        _decode_urlsafe(nonce),
        _decode_urlsafe(ciphertext),
        None,
    ).decode("utf-8")


def _encryption_key(secret):
    return hashlib.sha256(
        f"after-sales:erp-api-token:{secret}".encode("utf-8")
    ).digest()


def _decode_urlsafe(value):
    padding = "=" * (-len(value) % 4)
    return urlsafe_b64decode(
        f"{value}{padding}".encode("utf-8")
    )


def _fingerprint(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()[:12]


def _now():
    return datetime.now(timezone.utc).isoformat()
