#!/usr/bin/env python3
"""Seed (or reset) the E2E test user used by the Playwright smoke suite.

Usage:
    python scripts/seed_e2e_user.py                    # username/role/pwd defaults
    python scripts/seed_e2e_user.py --role adv         # provision an ADV instead
    E2E_TEST_PASSWORD=... python scripts/seed_e2e_user.py

The script reuses the same PostgreSQL store the FastAPI app uses, so the
seeded credentials work against any environment sharing that database
(local, staging). It is idempotent: on a re-run the password is reset
and the role realigned.

Warning: the default password is public — it is a *test-only* credential.
Never expose the seeded account outside dev / CI environments.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Make `src` importable when the script is launched from the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Load .env so PG_DATABASE_URL and friends are visible when the script is not
# launched via `docker compose exec`.
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

DEFAULT_USERNAME = "e2e-test-admin"
DEFAULT_PASSWORD = "E2E-Test-2026!"  # test-only, safe to commit
DEFAULT_ROLE = "admin"
DEFAULT_DISPLAY_NAME = "E2E Test Admin"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument(
        "--password",
        default=os.environ.get("E2E_TEST_PASSWORD", DEFAULT_PASSWORD),
        help="Test-only password (default: E2E-Test-2026!)",
    )
    parser.add_argument("--role", default=DEFAULT_ROLE, choices=["admin", "adv"])
    parser.add_argument("--display-name", default=DEFAULT_DISPLAY_NAME)
    args = parser.parse_args()

    from src.file2edi.store import get_store

    store = get_store()
    normalized = args.username.strip().lower()

    existing = next(
        (u for u in store.list_users() if str(u.get("username", "")).strip().lower() == normalized),
        None,
    )

    if existing:
        store.change_password(existing["userId"], args.password)
        if existing.get("role") != args.role:
            store.update_user(existing["userId"], role=args.role)
        print(f"reset user: {normalized} (role={args.role}, id={existing['userId']})")
    else:
        user = store.create_user(
            username=normalized,
            display_name=args.display_name,
            password=args.password,
            email=f"{normalized}@e2e.local",
            role=args.role,
        )
        print(f"created user: {normalized} (role={args.role}, id={user['userId']})")

    print()
    print("Set these env vars before running the smoke suite:")
    print(f'  $env:F2EDI_USER = "{normalized}"')
    print(f'  $env:F2EDI_PASSWORD = "{args.password}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
