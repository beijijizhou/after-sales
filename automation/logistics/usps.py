from datetime import datetime, timedelta, timezone
import hashlib
import threading
import time

import requests


class USPSClient:
    TOKEN_URL = "https://apis.usps.com/oauth2/v3/token"
    TRACKING_URL = "https://apis.usps.com/tracking/v3r2/tracking"
    _TOKEN_CACHE = {}
    _TOKEN_LOCK = threading.Lock()

    def __init__(self, client_id, client_secret, timeout=30):
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout

    def track(self, tracking_numbers):
        token = self._token()
        response = requests.post(
            self.TRACKING_URL,
            headers={"Authorization": f"Bearer {token}"},
            json=[{"trackingNumber": str(number)} for number in tracking_numbers],
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []

    def _token(self):
        cache_key = (
            self.client_id,
            hashlib.sha256(self.client_secret.encode()).hexdigest(),
        )
        with self._TOKEN_LOCK:
            cached = self._TOKEN_CACHE.get(cache_key)
            if cached and cached["expires_at"] > time.monotonic():
                return cached["token"]
            response = requests.post(
                self.TOKEN_URL,
                json={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            token = payload["access_token"]
            expires_in = max(int(payload.get("expires_in") or 28800), 120)
            self._TOKEN_CACHE[cache_key] = {
                "token": token,
                "expires_at": time.monotonic() + expires_in - 60,
            }
            return token


def classify_usps_response(package, cache_hours=1):
    events = package.get("trackingEvents") or []
    status = str(package.get("status") or "").strip()
    found = bool(status or events)
    return {
        "tracking_number": str(package.get("trackingNumber") or ""),
        "provider_status": status,
        "has_postal_record": found,
        "has_pre_scan": found,
        "response_payload": package,
        "error_code": str(
            package.get("errorCode") or package.get("error_code") or ""
        ),
        "cache_expires_at": (
            datetime.now(timezone.utc) + timedelta(hours=cache_hours)
        ).isoformat(),
    }
