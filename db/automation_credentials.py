"""Encrypted shared credentials for server-side ERP automation."""

from base64 import urlsafe_b64encode
from datetime import datetime, timezone
import hashlib

from cryptography.fernet import Fernet, InvalidToken


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
        return _cipher(encryption_secret).decrypt(
            str(row["encrypted_token"]).encode("utf-8")
        ).decode("utf-8")
    except (InvalidToken, KeyError, UnicodeDecodeError) as error:
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


def _fingerprint(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()[:12]


def _now():
    return datetime.now(timezone.utc).isoformat()
