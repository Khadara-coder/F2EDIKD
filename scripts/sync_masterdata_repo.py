#!/usr/bin/env python3
"""Daily masterdata sync job for production.

Workflow:
1. Fetch latest content from the configured git repository.
2. Validate required CSV files.
3. Publish validated files atomically to the target masterdata directory.
4. Write sync metadata with commit hash and file checksums.
5. Optionally notify File2EDI API to reload runtime cache.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

REQUIRED_FILES = [
    "10564_Customers.csv",
    "10564_Partners.csv",
    "10564_Materials.csv",
    "DB_Salesorder.csv",
]

DEFAULT_REPO_URL = "https://github.boschdevcloud.com/RSR1DY/masterdata.git"
DEFAULT_BRANCH = "main"
DEFAULT_METADATA_FILE = ".masterdata_sync_metadata.json"


def _ensure_git_available() -> None:
    if shutil.which("git"):
        return
    raise RuntimeError(
        "git binary not found in PATH. Install git in the runtime image "
        "(e.g. apt-get install git) or run scripts/sync_masterdata_repo.py on the host "
        "then call /api/masterdata/reload-cache."
    )


def _authenticated_repo_url(repo_url: str) -> str:
    """Inject MASTERDATA_GIT_TOKEN / GITHUB_TOKEN into HTTPS clone URL when set."""
    token = (
        os.environ.get("MASTERDATA_GIT_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
        or ""
    ).strip()
    if not token:
        return repo_url
    parsed = urlparse(repo_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return repo_url
    # Avoid double-embedding if the URL already contains userinfo.
    if parsed.username:
        return repo_url
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    netloc = f"x-access-token:{token}@{host}"
    return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "Command failed: {}\nstdout:\n{}\nstderr:\n{}".format(
                " ".join(cmd),
                proc.stdout.strip(),
                proc.stderr.strip(),
            )
        )
    return proc.stdout.strip()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _count_data_rows(path: Path) -> int:
    # Fast line-count approximation for CSV rows: total lines minus header.
    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        return max(0, sum(1 for _ in f) - 1)


def _prepare_worktree(repo_url: str, branch: str, worktree: Path) -> str:
    _ensure_git_available()
    auth_url = _authenticated_repo_url(repo_url)
    if not (worktree / ".git").exists():
        worktree.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--branch", branch, "--single-branch", auth_url, str(worktree)])
    else:
        _run(["git", "remote", "set-url", "origin", auth_url], cwd=worktree)
        _run(["git", "fetch", "origin", branch, "--prune"], cwd=worktree)
        _run(["git", "checkout", branch], cwd=worktree)
        _run(["git", "reset", "--hard", f"origin/{branch}"], cwd=worktree)

    _run(["git", "fetch", "origin", branch, "--prune"], cwd=worktree)
    _run(["git", "checkout", branch], cwd=worktree)
    _run(["git", "reset", "--hard", f"origin/{branch}"], cwd=worktree)
    commit = _run(["git", "rev-parse", "HEAD"], cwd=worktree)
    return commit


def _validate_required_files(worktree: Path) -> dict[str, dict[str, Any]]:
    file_info: dict[str, dict[str, Any]] = {}
    missing: list[str] = []

    for name in REQUIRED_FILES:
        p = worktree / name
        if not p.exists():
            missing.append(name)
            continue
        rows = _count_data_rows(p)
        file_info[name] = {
            "rows": rows,
            "sha256": _sha256(p),
            "size_bytes": p.stat().st_size,
        }

    if missing:
        raise RuntimeError("Missing required masterdata files: {}".format(", ".join(missing)))

    return file_info


def _atomic_publish(worktree: Path, target_dir: Path, metadata_file: str, metadata: dict[str, Any]) -> None:
    staging_dir = target_dir.parent / (target_dir.name + ".staging")
    backup_dir = target_dir.parent / (target_dir.name + ".previous")

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    for name in REQUIRED_FILES:
        shutil.copy2(worktree / name, staging_dir / name)

    metadata_path = staging_dir / metadata_file
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=True), encoding="utf-8")

    if backup_dir.exists():
        shutil.rmtree(backup_dir)

    if target_dir.exists():
        target_dir.rename(backup_dir)

    staging_dir.rename(target_dir)


def _notify_reload(api_url: str, api_key: str | None, timeout_s: int) -> dict[str, Any]:
    try:
        import requests
    except Exception as exc:
        raise RuntimeError("requests package is required for API notify: {}".format(exc))

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    resp = requests.post(api_url, headers=headers, json={}, timeout=timeout_s)
    body: dict[str, Any]
    try:
        body = resp.json() if resp.content else {}
    except Exception:
        body = {"raw": resp.text[:500]}

    if resp.status_code >= 400:
        raise RuntimeError("Reload API call failed ({}): {}".format(resp.status_code, body))

    return body


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily sync of masterdata.git into production directory")
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--target-dir", required=True, help="Destination directory used by File2EDI MASTERDATA_SOURCE_DIR")
    parser.add_argument("--work-root", default="", help="Working directory for local clone cache")
    parser.add_argument("--metadata-file", default=DEFAULT_METADATA_FILE)
    parser.add_argument("--notify-api-url", default="", help="Optional File2EDI endpoint, for example https://<host>/api/masterdata/sync")
    parser.add_argument("--notify-api-key", default="", help="Optional API key passed as x-api-key for notify call")
    parser.add_argument("--notify-timeout-s", type=int, default=30)
    args = parser.parse_args()

    target_dir = Path(args.target_dir).resolve()
    work_root = Path(args.work_root).resolve() if args.work_root else (target_dir.parent / ".masterdata_repo_cache")
    worktree = work_root / "repo"

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    work_root.mkdir(parents=True, exist_ok=True)

    try:
        commit = _prepare_worktree(args.repo_url, args.branch, worktree)
        file_info = _validate_required_files(worktree)
        synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        metadata = {
            "repo_url": args.repo_url,
            "branch": args.branch,
            "commit": commit,
            "synced_at_utc": synced_at,
            "required_files": list(REQUIRED_FILES),
            "files": file_info,
            "sync_runner": "scripts/sync_masterdata_repo.py",
        }

        _atomic_publish(worktree, target_dir, args.metadata_file, metadata)

        notify_result: dict[str, Any] | None = None
        if args.notify_api_url:
            notify_result = _notify_reload(
                args.notify_api_url,
                args.notify_api_key or None,
                args.notify_timeout_s,
            )

        output = {
            "status": "ok",
            "target_dir": str(target_dir),
            "metadata_file": str(target_dir / args.metadata_file),
            "synced_at_utc": synced_at,
            "repo_url": args.repo_url,
            "branch": args.branch,
            "commit": commit,
            "files": file_info,
            "notify": notify_result,
        }
        print(json.dumps(output, indent=2, ensure_ascii=True))
        return 0
    except Exception as exc:
        err = {
            "status": "error",
            "message": str(exc),
            "target_dir": str(target_dir),
            "repo_url": args.repo_url,
            "branch": args.branch,
        }
        print(json.dumps(err, indent=2, ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
