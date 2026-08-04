"""Sync masterdata from a Databricks Apps HTTP API into local CSV cache files.

Expected API shape (configurable paths in admin settings):
  GET {baseUrl}/health
  GET {baseUrl}/customers?limit=&offset=
  GET {baseUrl}/partners?limit=&offset=
  GET {baseUrl}/materials?limit=&offset=
  GET {baseUrl}/salesorders?limit=&offset=

Auth: Bearer token from DATABRICKS_TOKEN (or MASTERDATA_API_TOKEN override).
"""

from __future__ import annotations

import csv
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

log = logging.getLogger("edifact.masterdata_api_sync")

DEFAULT_BASE_URL = "https://masterdata-api-5555213114570927.7.azure.databricksapps.com"

RESOURCE_SPECS: dict[str, dict[str, Any]] = {
    "customers": {
        "filename": "10564_Customers.csv",
        "path_key": "customersPath",
        "default_path": "/customers",
        "columns": ["SOLDTO", "NAME", "ORT01", "PSTLZ", "STRAS", "LAND1", "VAT_NR"],
    },
    "partners": {
        "filename": "10564_Partners.csv",
        "path_key": "partnersPath",
        "default_path": "/partners",
        "columns": [
            "SOLDTO", "SHIPTO", "LAND1", "NAME", "ORT01", "PSTLZ", "STRAS", "PARVW",
            "Fonction-Partenaire", "Gestionaire-ADV", "Email-I.D", "User-I.D", "numero-personne",
        ],
    },
    "materials": {
        "filename": "10564_Materials.csv",
        "path_key": "materialsPath",
        "default_path": "/materials",
        "columns": ["MATNR", "MAKTX"],
    },
    "salesorders": {
        "filename": "DB_Salesorder.csv",
        "path_key": "salesordersPath",
        "default_path": "/salesorders",
        "columns": ["VBELN", "ERDAT", "ERNAM", "BSTNK", "BSTDK", "KUNNR"],
    },
}


def default_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "baseUrl": DEFAULT_BASE_URL,
        "healthPath": "/health",
        "customersPath": "/customers",
        "partnersPath": "/partners",
        "materialsPath": "/materials",
        "salesordersPath": "/salesorders",
        "pageSize": 5000,
    }


def resolve_config(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = default_config()
    if isinstance(raw, dict):
        for key in cfg:
            if key in raw and raw.get(key) is not None:
                cfg[key] = raw.get(key)
    cfg["baseUrl"] = str(cfg.get("baseUrl") or "").strip().rstrip("/")
    cfg["enabled"] = bool(cfg.get("enabled"))
    try:
        cfg["pageSize"] = max(100, min(20000, int(cfg.get("pageSize") or 5000)))
    except (TypeError, ValueError):
        cfg["pageSize"] = 5000
    for path_key in (
        "healthPath",
        "customersPath",
        "partnersPath",
        "materialsPath",
        "salesordersPath",
    ):
        path = str(cfg.get(path_key) or "").strip() or default_config()[path_key]
        if not path.startswith("/"):
            path = "/" + path
        cfg[path_key] = path
    return cfg


def _auth_token() -> str:
    return (
        os.environ.get("MASTERDATA_API_TOKEN")
        or os.environ.get("DATABRICKS_TOKEN")
        or ""
    ).strip()


def _headers() -> dict[str, str]:
    token = _auth_token()
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _join(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "data", "results", "rows", "customers", "partners", "materials", "salesorders"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    # Single object response
    if any(k.isupper() for k in payload.keys()):
        return [payload]
    return []


def test_connection(config: dict[str, Any] | None = None) -> tuple[bool, str]:
    """Probe health endpoint with current token/settings."""
    import requests

    cfg = resolve_config(config)
    if not cfg["baseUrl"]:
        return False, "URL masterdata API non configurée"
    if not _auth_token():
        return False, "DATABRICKS_TOKEN manquant (Paramètres > IA)"

    url = _join(cfg["baseUrl"], cfg["healthPath"])
    try:
        resp = requests.get(url, headers=_headers(), timeout=15)
    except Exception as exc:
        return False, f"Connexion impossible: {exc}"

    if resp.status_code in {401, 403}:
        return False, f"Auth refusée ({resp.status_code}) — vérifiez le token Databricks"
    if resp.status_code >= 400:
        return False, f"HTTP {resp.status_code}: {(resp.text or '')[:180]}"

    # Databricks Apps may return HTML login when auth is missing/invalid.
    content_type = (resp.headers.get("content-type") or "").lower()
    body = (resp.text or "").lstrip()
    if "text/html" in content_type or body.lower().startswith("<!doctype"):
        return False, "Réponse HTML (login Databricks) — token manquant ou invalide"

    try:
        data = resp.json()
        detail = json.dumps(data, ensure_ascii=False)[:120]
    except Exception:
        detail = (resp.text or "")[:120]
    return True, f"API joignable ({cfg['baseUrl']}) — {detail}"


def _fetch_all_rows(session, base_url: str, path: str, page_size: int) -> list[dict[str, Any]]:
    import requests

    rows: list[dict[str, Any]] = []
    offset = 0
    max_pages = 500
    for _ in range(max_pages):
        url = _join(base_url, path)
        resp = session.get(
            url,
            headers=_headers(),
            params={"limit": page_size, "offset": offset},
            timeout=120,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code} on {path}: {(resp.text or '')[:240]}")
        content_type = (resp.headers.get("content-type") or "").lower()
        body = (resp.text or "").lstrip()
        if "text/html" in content_type or body.lower().startswith("<!doctype"):
            raise RuntimeError(
                f"Auth HTML reçue sur {path} — configurez DATABRICKS_TOKEN (Paramètres > IA)"
            )
        try:
            payload = resp.json()
        except Exception as exc:
            raise RuntimeError(f"JSON invalide sur {path}: {exc}") from exc

        batch = _extract_rows(payload)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=columns,
            delimiter=";",
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        written = 0
        for row in rows:
            out = {col: "" if row.get(col) is None else str(row.get(col)) for col in columns}
            # Case-insensitive fallback for API field names.
            lower_map = {str(k).lower(): v for k, v in row.items()}
            for col in columns:
                if out[col] == "" and col.lower() in lower_map:
                    val = lower_map[col.lower()]
                    out[col] = "" if val is None else str(val)
            writer.writerow(out)
            written += 1
    return written


def sync_from_api(
    *,
    target_dir: str | Path,
    config: dict[str, Any] | None = None,
    metadata_filename: str = ".masterdata_sync_metadata.json",
) -> dict[str, Any]:
    """Download all masterdata resources and publish CSVs atomically."""
    import requests

    cfg = resolve_config(config)
    if not cfg["enabled"]:
        raise RuntimeError("API masterdata désactivée dans les paramètres admin")
    if not cfg["baseUrl"]:
        raise RuntimeError("URL masterdata API vide")
    if not _auth_token():
        raise RuntimeError("DATABRICKS_TOKEN manquant (Paramètres > IA)")

    target = Path(target_dir).resolve()
    staging = target.parent / (target.name + ".api_staging")
    if staging.exists():
        import shutil

        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    files_info: dict[str, dict[str, Any]] = {}
    with requests.Session() as session:
        health_url = _join(cfg["baseUrl"], cfg["healthPath"])
        health_resp = session.get(health_url, headers=_headers(), timeout=15)
        if health_resp.status_code in {401, 403}:
            raise RuntimeError(
                f"Auth refusée ({health_resp.status_code}) — vérifiez le token Databricks"
            )
        if health_resp.status_code >= 400:
            raise RuntimeError(
                f"Health HTTP {health_resp.status_code}: {(health_resp.text or '')[:180]}"
            )
        health_ct = (health_resp.headers.get("content-type") or "").lower()
        health_body = (health_resp.text or "").lstrip()
        if "text/html" in health_ct or health_body.lower().startswith("<!doctype"):
            raise RuntimeError(
                "Réponse HTML (login Databricks) — token manquant ou invalide"
            )

        for key, spec in RESOURCE_SPECS.items():
            path = str(cfg.get(spec["path_key"]) or spec["default_path"])
            rows = _fetch_all_rows(session, cfg["baseUrl"], path, int(cfg["pageSize"]))
            out_path = staging / spec["filename"]
            count = _write_csv(out_path, list(spec["columns"]), rows)
            files_info[spec["filename"]] = {
                "rows": count,
                "resource": key,
                "path": path,
            }
            log.info("masterdata api sync: %s → %s rows=%s", key, spec["filename"], count)

    # Atomic publish: replace target contents with staging files.
    target.mkdir(parents=True, exist_ok=True)
    for name, info in files_info.items():
        src = staging / name
        dst = target / name
        dst.write_bytes(src.read_bytes())

    synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    metadata = {
        "source": "masterdata_api",
        "base_url": cfg["baseUrl"],
        "synced_at_utc": synced_at,
        "files": files_info,
        "sync_runner": "src.masterdata_api_sync",
    }
    (target / metadata_filename).write_text(
        json.dumps(metadata, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    import shutil

    shutil.rmtree(staging, ignore_errors=True)

    return {
        "status": "ok",
        "source": "masterdata_api",
        "base_url": cfg["baseUrl"],
        "synced_at_utc": synced_at,
        "files": files_info,
        "target_dir": str(target),
    }
