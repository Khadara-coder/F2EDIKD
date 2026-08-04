"""Quick non-regression smoke checks for critical File2EDI API endpoints.

Usage:
  python scripts/smoke_file2edi_api.py
  python scripts/smoke_file2edi_api.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    skipped: bool = False


def get_json(url: str, cookie: str = "") -> tuple[int, dict]:
    # Avoid corporate/system proxy interception for local loopback checks.
    opener = build_opener(ProxyHandler({}))
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    req = Request(url, method="GET", headers=headers)
    with opener.open(req, timeout=10) as resp:
        payload = resp.read().decode("utf-8", errors="replace")
        return resp.status, json.loads(payload) if payload else {}


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
        if first.startswith("f2edi_session=") or first.startswith("f2edi_profile_session="):
            return first
    return ""


def run_check(name: str, fn) -> CheckResult:
    try:
        return fn()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        return CheckResult(name, False, f"HTTP {exc.code}: {body}")
    except URLError as exc:
        return CheckResult(name, False, f"Connection error: {exc.reason}")
    except Exception as exc:  # noqa: BLE001
        return CheckResult(name, False, f"{type(exc).__name__}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="FastAPI base URL")
    parser.add_argument("--actor", default="", help="Login actor for protected endpoints")
    parser.add_argument("--password", default="", help="Login password for protected endpoints")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    cookie = ""
    if args.actor and args.password:
        try:
            cookie = login_cookie(base, args.actor, args.password)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] login failed: {type(exc).__name__}: {exc}")

    def check_health() -> CheckResult:
        status, data = get_json(f"{base}/api/health/system")
        required = {"api", "database", "csv", "sftp"}
        missing = sorted(required - set(data))
        if status != 200:
            return CheckResult("health", False, f"unexpected status: {status}")
        if missing:
            return CheckResult("health", False, f"missing keys: {', '.join(missing)}")
        return CheckResult("health", True, f"ok ({data.get('databaseBackend', 'unknown')} backend)")

    def check_dashboard_metrics() -> CheckResult:
        try:
            status, data = get_json(f"{base}/api/dashboard/metrics", cookie=cookie)
        except HTTPError as exc:
            if exc.code == 401 and not cookie:
                return CheckResult("dashboard_metrics", True, "skipped (auth required, provide --actor/--password)", skipped=True)
            raise
        if status != 200:
            return CheckResult("dashboard_metrics", False, f"unexpected status: {status}")
        if "total" not in data:
            return CheckResult("dashboard_metrics", False, "missing key: total")
        return CheckResult("dashboard_metrics", True, f"ok (total={data.get('total')})")

    def check_review_queue() -> CheckResult:
        try:
            status, data = get_json(f"{base}/api/dashboard/review-queue", cookie=cookie)
        except HTTPError as exc:
            if exc.code == 401 and not cookie:
                return CheckResult("review_queue", True, "skipped (auth required, provide --actor/--password)", skipped=True)
            raise
        if status != 200:
            return CheckResult("review_queue", False, f"unexpected status: {status}")
        if not isinstance(data, list):
            return CheckResult("review_queue", False, "payload is not a list")
        return CheckResult("review_queue", True, f"ok ({len(data)} item(s))")

    def check_orders() -> CheckResult:
        try:
            status, data = get_json(f"{base}/api/orders", cookie=cookie)
        except HTTPError as exc:
            if exc.code == 401 and not cookie:
                return CheckResult("orders", True, "skipped (auth required, provide --actor/--password)", skipped=True)
            raise
        if status != 200:
            return CheckResult("orders", False, f"unexpected status: {status}")
        if not isinstance(data, list):
            return CheckResult("orders", False, "payload is not a list")
        return CheckResult("orders", True, f"ok ({len(data)} item(s))")

    checks = [
        ("health", check_health),
        ("dashboard_metrics", check_dashboard_metrics),
        ("review_queue", check_review_queue),
        ("orders", check_orders),
    ]

    results = [run_check(name, fn) for name, fn in checks]
    failed = [r for r in results if not r.ok]

    for r in results:
        icon = "SKIP" if r.skipped else ("OK" if r.ok else "FAIL")
        print(f"[{icon}] {r.name}: {r.detail}")

    if failed:
        print(f"\n{len(failed)} check(s) failed.")
        return 1
    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
