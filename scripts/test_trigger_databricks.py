"""Smoke test: configure the Databricks job + trigger it via File2EDI API."""

from __future__ import annotations

import json
import os
import sys
from urllib.request import Request, build_opener, ProxyHandler


def login(base: str, actor: str, password: str) -> str:
    opener = build_opener(ProxyHandler({}))
    req = Request(
        f"{base}/api/auth/login",
        method="POST",
        data=json.dumps({"actor": actor, "password": password}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with opener.open(req, timeout=10) as resp:
        cookies = resp.headers.get_all("Set-Cookie") or []
    for raw in cookies:
        first = raw.split(";", 1)[0]
        if first.startswith(("f2edi_session=", "f2edi_profile_session=")):
            return first
    raise RuntimeError(f"login failed: {cookies}")


def call(base: str, method: str, path: str, body: dict | None, cookie: str) -> tuple[int, dict]:
    opener = build_opener(ProxyHandler({}))
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = Request(
        f"{base}{path}",
        method=method,
        data=data,
        headers={"Content-Type": "application/json", "Cookie": cookie},
    )
    try:
        with opener.open(req, timeout=60) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(text) if text else {}
    except Exception as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            detail = str(exc)
        try:
            return int(getattr(exc, "code", 0)) or 599, json.loads(detail)
        except Exception:
            return int(getattr(exc, "code", 0)) or 599, {"raw": detail}


def main() -> int:
    base = os.environ.get("F2EDI_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    actor = os.environ.get("F2EDI_ACTOR", "khadara")
    password = os.environ["F2EDI_PASSWORD"]
    job_id = os.environ.get("DATABRICKS_JOB_ID", "21640086401825")
    host = os.environ.get(
        "DATABRICKS_HOST", "https://adb-5555213114570927.7.azuredatabricks.net"
    )

    print(f"→ login {actor} @ {base}")
    cookie = login(base, actor, password)

    print(f"\n→ read current settings")
    status, settings = call(base, "GET", "/api/settings", None, cookie)
    if status != 200:
        print(f"failed: HTTP {status}")
        print(json.dumps(settings, indent=2)[:400])
        return 1

    current = settings.get("masterdataDatabricksJobConfig") or {}
    print(f"  current: {json.dumps(current, ensure_ascii=False)}")

    print(f"\n→ PUT masterdataDatabricksJobConfig  host={host}  jobId={job_id}")
    status, body = call(
        base, "PUT", "/api/settings",
        {
            "masterdataDatabricksJobConfig": {
                "enabled": True,
                "host": host,
                "jobId": job_id,
            }
        },
        cookie,
    )
    print(f"  HTTP {status}")
    saved = (body.get("masterdataDatabricksJobConfig") if isinstance(body, dict) else None) or {}
    print(f"  saved:   {json.dumps(saved, ensure_ascii=False)}")

    print(f"\n→ POST /api/masterdata/trigger-databricks-job")
    status, body = call(base, "POST", "/api/masterdata/trigger-databricks-job", None, cookie)
    print(f"  HTTP {status}")
    print(json.dumps(body, indent=2, ensure_ascii=False)[:1500])
    if status != 200:
        return 2

    print(f"\n→ check sync history")
    status, body = call(base, "GET", "/api/masterdata/sync-history?limit=5", None, cookie)
    for ev in (body.get("events") or [])[:5]:
        d = ev.get("details") or {}
        print(f"  · {ev.get('createdAt')}  {ev.get('action'):45s} {ev.get('result'):8s}  "
              f"run={d.get('run_id')}  url={d.get('run_page_url')}")

    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
