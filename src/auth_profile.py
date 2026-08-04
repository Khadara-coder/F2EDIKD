"""Profile-login helpers extracted from the FastAPI monolith."""

from __future__ import annotations

import os


def get_profile_login_password() -> str:
    """Return configured shared profile password (empty if unset).

    Security: no implicit default password. Operators must set
    APP_PROFILE_LOGIN_PASSWORD explicitly when ENABLE_PROFILE_LOGIN is on.
    """
    return (os.environ.get("APP_PROFILE_LOGIN_PASSWORD") or "").strip()


def is_profile_login_password_configured() -> bool:
    return bool(get_profile_login_password())
