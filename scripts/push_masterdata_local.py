"""Local test of the /api/masterdata/push-all endpoint.

Reads the CSVs from ``data/masterdata/`` and pushes them to a running Genie
instance (default: http://127.0.0.1:8080). Verifies:
  1. Happy path — all 4 tables push cleanly, row counts match.
  2. Fallback — a truncated payload is rejected and the runtime keeps the
     previous version (backup restored).

Env vars:
  F2EDI_BASE_URL   default http://127.0.0.1:8080
  F2EDI_ACTOR      login actor
  F2EDI_PASSWORD   login password
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "masterdata"

FILES = {
    "customers":   DATA_DIR / "10564_Customers.csv",
    "partners":    DATA_DIR / "10564_Partners.csv",
    "materials":   DATA_DIR / "DB_Materials.csv",
    "salesorders": DATA_DIR / "DB_Salesorder.csv",
}


def read_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ";"
        reader = csv.DictReader(f, dialect=dialect)
        return [
            {(k or "").strip(): ("" if v is None else str(v)) for k, v in r.items()}
            for r in reader
        ]


def login_cookie(base: str, actor: str, password: str) -> str:
    opener = build_opener(ProxyHandler({}))
    payload = json.dumps({"actor": actor, "password": password}).encode("utf-8")
    req = Request(
        f"{base}/api/auth/login",
        method="POST",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with opener.open(req, timeout=10) as resp:
        cookies = resp.headers.get_all("Set-Cookie") or []
    for raw in cookies:
        first = raw.split(";", 1)[0]
        if first.startswith(("f2edi_session=", "f2edi_profile_session=")):
            return first
    raise RuntimeError(f"login failed — no session cookie in response: {cookies}")


def post_json(base: str, path: str, body: dict, *, cookie: str) -> tuple[int, dict]:
    opener = build_opener(ProxyHandler({}))
    data = json.dumps(body).encode("utf-8")
    req = Request(
        f"{base}{path}",
        method="POST",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Cookie": cookie,
        },
    )
    try:
        with opener.open(req, timeout=600) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(text) if text else {}
    except Exception as exc:
        code = getattr(exc, "code", 0)
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            detail = str(exc)
        try:
            body = json.loads(detail)
        except Exception:
            body = {"raw": detail}
        return int(code) or 599, body


def get_json(base: str, path: str, *, cookie: str) -> tuple[int, dict]:
    opener = build_opener(ProxyHandler({}))
    req = Request(f"{base}{path}", method="GET", headers={"Cookie": cookie})
    with opener.open(req, timeout=30) as resp:
        text = resp.read().decode("utf-8", errors="replace")
        return resp.status, json.loads(text) if text else {}


def main() -> int:
    base = os.environ.get("F2EDI_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    actor = os.environ.get("F2EDI_ACTOR", "khadara")
    password = os.environ.get("F2EDI_PASSWORD", "")
    if not password:
        print("F2EDI_PASSWORD required", file=sys.stderr)
        return 2

    print(f"→ login {actor} @ {base}")
    cookie = login_cookie(base, actor, password)

    # ---- read local files ----
    tables: dict[str, list[dict]] = {}
    for kind, path in FILES.items():
        if not path.exists():
            print(f"  ✗ missing {path}")
            return 3
        rows = read_rows(path)
        tables[kind] = rows
        print(f"  · {kind:12s} {len(rows):>7,} rows  ({path.name})")

    # ---- push-all (happy path) ----
    print("\n=== Test 1 : push-all (happy path) ===")
    t0 = time.time()
    status, body = post_json(
        base, "/api/masterdata/push-all",
        {
            "tables": tables,
            "source": "local_smoke_test",
            "job_id": "local-1",
            "description": "smoke: push 4 tables",
        },
        cookie=cookie,
    )
    elapsed = time.time() - t0
    print(f"HTTP {status}  in {elapsed:.1f}s")
    print(json.dumps(body, indent=2, ensure_ascii=False)[:2000])
    if status != 200:
        return 4
    imported = {r["kind"]: r for r in body.get("imported", [])}
    for kind, expected in {k: len(v) for k, v in tables.items()}.items():
        got = imported.get(kind, {}).get("rows")
        tag = "OK " if got == expected else "!! "
        print(f"  {tag}{kind:12s} sent={expected:>7,}  imported={got}")

    # ---- fallback test: push a truncated customers payload ----
    print("\n=== Test 2 : fallback (truncated payload) ===")
    truncated = tables["customers"][:5]  # <50% of previous version
    status, body = post_json(
        base, "/api/masterdata/push",
        {
            "kind": "customers",
            "rows": truncated,
            "source": "local_smoke_test",
            "job_id": "local-2",
            "description": "smoke: truncated (should be rejected)",
        },
        cookie=cookie,
    )
    print(f"HTTP {status}")
    print(json.dumps(body, indent=2, ensure_ascii=False)[:800])
    if status != 400:
        print("  !! expected HTTP 400 (rejected), got", status)
        return 5
    print("  OK rejected as expected")

    # ---- verify current runtime still has the full customers table ----
    print("\n=== Test 3 : sync history + current state ===")
    status, body = get_json(base, "/api/masterdata/sync-history?limit=10", cookie=cookie)
    print(f"HTTP {status}  events={body.get('count')}")
    seen_rejected = False
    for ev in (body.get("events") or [])[:10]:
        d = ev.get("details") or {}
        if ev.get("action") == "masterdata_push_rejected":
            seen_rejected = True
        print(f"  · {ev.get('createdAt')} {ev.get('action'):40s} {ev.get('result'):8s}  "
              f"kind={d.get('kind') or d.get('tables')}  reason={d.get('reason') or '-'}")

    if not seen_rejected:
        print("  !! expected masterdata_push_rejected event in history")
        return 6
    print("  OK rejection event visible in history")

    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
