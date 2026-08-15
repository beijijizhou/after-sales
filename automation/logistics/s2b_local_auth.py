"""Compatibility imports for the S2B provider authentication fallback."""

from automation.api.s2b.local_auth import (
    S2BLocalLoginRequired,
    local_login_available,
    refresh_local_s2b_token,
)

__all__ = [
    "S2BLocalLoginRequired",
    "local_login_available",
    "refresh_local_s2b_token",
]
