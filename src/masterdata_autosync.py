"""Automatic masterdata synchronization from the Git snapshot repo.

Designed to run as a background loop inside the FastAPI process, or via an
external scheduler calling scripts/sync_masterdata_repo.py.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("edifact.masterdata_autosync")

DEFAULT_REPO_URL = "https://github.boschdevcloud.com/RSR1DY/masterdata.git"
DEFAULT_BRANCH = "main"
DEFAULT_INTERVAL_HOURS = 24


def auto_sync_enabled() -> bool:
    return os.environ.get("MASTERDATA_AUTO_SYNC", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def auto_sync_interval_hours() -> float:
    raw = (os.environ.get("MASTERDATA_AUTO_SYNC_INTERVAL_HOURS") or str(DEFAULT_INTERVAL_HOURS)).strip()
    try:
        value = float(raw)
    except ValueError:
        return float(DEFAULT_INTERVAL_HOURS)
    return max(1.0, value)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def run_repo_sync(
    *,
    target_dir: str | None = None,
    repo_url: str | None = None,
    branch: str | None = None,
    notify_api_url: str | None = None,
    notify_api_key: str | None = None,
) -> dict:
    """Run scripts/sync_masterdata_repo.py and return parsed JSON output."""
    root = _repo_root()
    script = root / "scripts" / "sync_masterdata_repo.py"
    if not script.exists():
        raise FileNotFoundError(f"Sync script missing: {script}")

    target = target_dir or os.environ.get("MASTERDATA_RUNTIME_DIR") or str(root / "data" / "masterdata")
    repo = repo_url or os.environ.get("MASTERDATA_REPO_URL") or DEFAULT_REPO_URL
    br = branch or os.environ.get("MASTERDATA_REPO_BRANCH") or DEFAULT_BRANCH
    notify = notify_api_url if notify_api_url is not None else os.environ.get("MASTERDATA_NOTIFY_API_URL", "")
    api_key = notify_api_key if notify_api_key is not None else os.environ.get("MASTERDATA_NOTIFY_API_KEY", "")

    cmd = [
        sys.executable,
        str(script),
        "--repo-url",
        repo,
        "--branch",
        br,
        "--target-dir",
        str(Path(target).resolve()),
    ]
    if notify:
        cmd.extend(["--notify-api-url", notify])
    if api_key:
        cmd.extend(["--notify-api-key", api_key])

    log.info("masterdata autosync: starting repo sync (%s @ %s -> %s)", repo, br, target)
    proc = subprocess.run(
        cmd,
        cwd=str(root),
        text=True,
        capture_output=True,
        check=False,
    )
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        raise RuntimeError(
            f"masterdata autosync failed (exit={proc.returncode}): {stderr or stdout or 'no output'}"
        )

    import json

    try:
        payload = json.loads(stdout) if stdout else {"status": "ok", "raw": stdout}
    except json.JSONDecodeError:
        payload = {"status": "ok", "raw": stdout}

    payload["finished_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log.info(
        "masterdata autosync: success commit=%s files=%s",
        payload.get("commit"),
        list((payload.get("files") or {}).keys()),
    )
    return payload
