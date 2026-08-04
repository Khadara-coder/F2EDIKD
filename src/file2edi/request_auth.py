"""Request-scoped auth helpers for File2EDI router.

Keeps FastAPI Request handling in one place. Identity resolution still
delegates to server for session/cookie/API-key awareness until that logic
is fully extracted.
"""

from __future__ import annotations

from typing import Any


def resolve_actor(req: Any = None, payload: dict | None = None) -> str:
    import server as srv

    return srv._resolve_actor(req, payload)


def resolve_role(actor: str) -> str:
    import server as srv

    return srv._resolve_role(actor)


def resolve_role_for_request(actor: str, req: Any = None) -> str:
    import server as srv

    return srv._resolve_role_for_request(actor, req)


def ensure_admin(req: Any = None, payload: dict | None = None) -> tuple[str, str]:
    import server as srv

    return srv._ensure_admin(req, payload)
