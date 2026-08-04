"""Pure actor/role identity helpers (no FastAPI Request, no server import)."""

from __future__ import annotations

import os
import re


def parse_csv_env(name: str) -> set[str]:
    """Parse a comma-separated env var into a lowercase set."""
    raw = os.environ.get(name, "")
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def normalize_actor_identity(value: str | None) -> str:
    """Normalize actor identifiers for role lookups and persistence."""
    v = (value or "").strip().strip('"').strip("'")
    if not v:
        return ""
    lower = v.lower()
    if "@" in v:
        return v.lower()
    if "/" in v:
        tail = v.replace("\\", "/").split("/")[-1].strip()
        return tail.lower()
    if lower.startswith("users:"):
        return lower.split(":", 1)[1].strip()
    if lower.startswith("user:"):
        return lower.split(":", 1)[1].strip()
    return lower


def display_name_from_actor(actor: str) -> str:
    """Derive a readable first/last name from an email-like actor identifier."""
    normalized = normalize_actor_identity(actor)
    if not normalized:
        return ""
    local = normalized.split("@", 1)[0]
    local = local.replace("users:", "").replace("user:", "")
    parts = [part for part in re.split(r"[._\-]+", local) if part]
    if not parts:
        return normalized

    def _titleize(part: str) -> str:
        return part[:1].upper() + part[1:].lower() if part else ""

    return " ".join(_titleize(part) for part in parts)


def resolve_role_from_env(actor: str) -> str:
    """Resolve role with the 2-role model: admin or adv (env-based)."""
    a = normalize_actor_identity(actor)
    if a in parse_csv_env("APP_ADMIN_USERS"):
        return "admin"
    # Legacy vars treated as adv for backward compatibility.
    _ = parse_csv_env("APP_REVIEW_USERS") | parse_csv_env("APP_READONLY_USERS")
    return "adv"


def actor_folder_name(actor: str | None) -> str:
    """Normalize actor into a filesystem-safe folder name."""
    raw = (actor or "").strip().lower()
    if not raw:
        return "operator"
    raw = raw.replace("\\", "/").split("/")[-1]
    safe = "".join(ch if (ch.isalnum() or ch in ("-", "_", ".")) else "_" for ch in raw)
    safe = safe.strip("._-")
    return safe[:80] or "operator"
