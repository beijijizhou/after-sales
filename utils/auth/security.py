import base64
import hashlib
import hmac
import os

import streamlit as st


def hash_password(password):
    salt = base64.urlsafe_b64encode(os.urandom(16)).decode("utf-8").rstrip("=")
    iterations = 260000
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    password_hash = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return f"pbkdf2_sha256${iterations}${salt}${password_hash}"


def verify_password(password, stored_hash):
    if not stored_hash:
        return False

    if not str(stored_hash).startswith("pbkdf2_sha256$"):
        return hmac.compare_digest(str(stored_hash), password)

    try:
        _, iterations, salt, password_hash = str(stored_hash).split("$", 3)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        )
        expected_hash = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
        return hmac.compare_digest(expected_hash, password_hash)
    except Exception:
        return False


def get_auth_secret():
    return str(st.secrets.get("AUTH_TOKEN_SECRET") or st.secrets.get("SUPABASE_KEY") or "after-sales")


def build_auth_token(username):
    username = str(username).strip()
    signature = hmac.new(
        get_auth_secret().encode("utf-8"),
        username.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    payload = f"{username}:{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("utf-8").rstrip("=")


def parse_auth_token(token):
    try:
        padded_token = token + "=" * (-len(token) % 4)
        payload = base64.urlsafe_b64decode(padded_token.encode("utf-8")).decode("utf-8")
        username, signature = payload.rsplit(":", 1)
        expected_signature = hmac.new(
            get_auth_secret().encode("utf-8"),
            username.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            return None
        return username
    except Exception:
        return None
