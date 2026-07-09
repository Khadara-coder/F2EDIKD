"""EDIFACT Generator — FastAPI REST API + File2EDI React SPA.

Bosch Thermotechnologie France / ELM_STANDARD D.96A ORDERS
Entry:  uvicorn server:app --host=0.0.0.0 --port=8000
UI:     frontend/dist (React + Vite)
API:    /api/*
"""
from __future__ import annotations

import hashlib
import hmac
from collections import OrderedDict
import json
import logging
import os
import shutil
import sqlite3
from datetime import datetime as _datetime
import sys
import tempfile
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("edifact.server")

# ── Path injection ─────────────────────────────────────────────────────────────
APP_ROOT = Path(__file__).resolve().parent
SRC_ROOT = APP_ROOT / "src"
for _p in (str(APP_ROOT), str(SRC_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ── Dir helper (FUSE-safe fallback for /Workspace paths in container) ──────────
def _ensure_dir(preferred: str, fallback_name: str) -> str:
    try:
        Path(preferred).mkdir(parents=True, exist_ok=True)
        return preferred
    except (PermissionError, OSError):
        local = APP_ROOT / "data" / fallback_name
        local.mkdir(parents=True, exist_ok=True)
        return str(local)


# ── Runtime configuration ──────────────────────────────────────────────────────
ENGINE_DIR          = os.environ.get("ENGINE_DIR",   str(APP_ROOT))
MASTER_DATA_SRC     = os.environ.get("MASTERDATA_SOURCE_DIR",
                          "/Workspace/Users/rsr1dy@bosch.com/masterdata")
MASTER_DATA_RUNTIME = _ensure_dir(
    os.environ.get("MASTERDATA_RUNTIME_DIR", str(APP_ROOT / "data" / "masterdata")),
    "masterdata",
)
OUTBOX_DIR = _ensure_dir(
    os.environ.get("OUTBOX_DIR", str(APP_ROOT / "data" / "outbox")),
    "outbox",
)
LOG_DIR = _ensure_dir(
    os.environ.get("LOG_DIR", str(APP_ROOT / "data" / "logs")),
    "logs",
)
PDF_STORAGE_DIR = _ensure_dir(
    os.environ.get("PDF_STORAGE_DIR", os.environ.get("INTAKE_DIR", str(APP_ROOT / "data" / "intake"))),
    "intake",
)
# DB_PATH must be FUSE-safe: prefer ENGINE_DIR/data, fallback to APP_ROOT/data
# (matches the same pattern used by OUTBOX_DIR/LOG_DIR)
_db_path_env = (os.environ.get("DB_PATH") or "").strip()
if _db_path_env:
    _db_parent = _ensure_dir(str(Path(_db_path_env).parent), "db")
    DB_PATH = str(Path(_db_parent) / Path(_db_path_env).name)
else:
    _db_dir = _ensure_dir(os.path.join(ENGINE_DIR, "data"), "db")
    DB_PATH = os.path.join(_db_dir, "edifact_standalone.db")
CONFIG_INI       = os.path.join(ENGINE_DIR, "config.ini")
UNB_SENDER_GLN   = os.environ.get("UNB_SENDER_GLN",   "4399901876613")
UNB_RECEIVER_GLN = os.environ.get("UNB_RECEIVER_GLN", "3015981600108")
MODEL_ENDPOINT   = os.environ.get("DATABRICKS_MODEL_ENDPOINT", "databricks-gpt-oss-120b")
DATABRICKS_HOST  = os.environ.get("DATABRICKS_HOST",
                       "https://adb-5555213114570927.7.azuredatabricks.net")
F2EDI_API_BASE   = os.environ.get("F2EDI_API_BASE",
                       "https://file2edi-5555213114570927.7.azure.databricksapps.com")
AI_ENDPOINT_URL  = f"{DATABRICKS_HOST.rstrip('/')}/serving-endpoints/{MODEL_ENDPOINT}/invocations"

# Set MASTER_DATA_DIR for app/masterdata.py (read at import time)
os.environ.setdefault("MASTER_DATA_DIR", MASTER_DATA_RUNTIME)


# ── Environment detection (local dev vs Databricks Apps) ───────────────────────
def _detect_databricks_runtime() -> bool:
    """True when running inside a Databricks App / cluster, False for local dev."""
    for var in ("DATABRICKS_APP_NAME", "DATABRICKS_APP_PORT",
                "DATABRICKS_RUNTIME_VERSION", "DB_IS_DRIVER"):
        if os.environ.get(var):
            return True
    # Databricks Apps mount code under /Workspace or expose FUSE volumes
    return os.path.isdir("/Volumes") and os.path.isdir("/databricks")


IS_DATABRICKS = _detect_databricks_runtime()
IS_LOCAL = not IS_DATABRICKS
# Optional dev identity so local runs mirror the Databricks SSO actor/role flow
# (respects APP_ADMIN_USERS / APP_REVIEW_USERS RBAC instead of bypassing it).
DEV_ACTOR = (os.environ.get("DEV_ACTOR") or "").strip().lower()
_profile_login_default = "false" if IS_DATABRICKS else "true"
ENABLE_PROFILE_LOGIN = os.environ.get("ENABLE_PROFILE_LOGIN", _profile_login_default).strip().lower() in {
    "1", "true", "yes", "on"
}
SESSION_COOKIE_NAME = "f2edi_profile_session"
SESSION_TTL_SECONDS = int(os.environ.get("PROFILE_SESSION_TTL_SECONDS", "28800") or "28800")
_PROFILE_SESSIONS: dict[str, dict] = {}
log.info("environment: %s (databricks=%s dev_actor=%s)",
         "DATABRICKS" if IS_DATABRICKS else "LOCAL", IS_DATABRICKS, DEV_ACTOR or "-")


# ── Auth helper ────────────────────────────────────────────────────────────────
def _auth_headers() -> dict:
    """Bearer auth: explicit token → Databricks CLI profile / SP OAuth.

    Locally this resolves through DATABRICKS_CONFIG_PROFILE (e.g. `Khadara`)
    so the LLM serving endpoint behaves the same as on Databricks Apps.
    """
    token = os.environ.get("DATABRICKS_TOKEN", "")
    if token:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        from databricks.sdk import WorkspaceClient
        profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", "").strip()
        w = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
        h = w.config.authenticate()
        h["Content-Type"] = "application/json"
        return h
    except Exception as exc:
        hint = (" — set DATABRICKS_CONFIG_PROFILE (ex: Khadara) or DATABRICKS_TOKEN"
                if IS_LOCAL else "")
        return {"Content-Type": "application/json", "_auth_error": f"{exc}{hint}"}


def _parse_csv_env(name: str) -> set[str]:
    """Parse a comma-separated env var into a lowercase set."""
    raw = os.environ.get(name, "")
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def _parse_secret_env(name: str) -> list[str]:
    """Parse a comma-separated env var without altering secret casing."""
    raw = os.environ.get(name, "")
    if not raw:
        return []
    values: list[str] = []
    for part in raw.replace(";", ",").split(","):
        token = part.strip()
        if token and token not in values:
            values.append(token)
    return values


def _normalize_actor_identity(value: str | None) -> str:
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


def _db_role_override(actor: str) -> str | None:
    """Return explicit DB role assignment for actor when present and active."""
    a = _normalize_actor_identity(actor)
    if not a:
        return None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        row = conn.execute(
            "SELECT role FROM user_roles WHERE actor=? AND is_active=1 LIMIT 1",
            [a],
        ).fetchone()
        conn.close()
        if not row or not row[0]:
            return None
        role = str(row[0]).strip().lower()
        return role if role in {"admin", "adv"} else None
    except Exception:
        return None


def _profile_session_data(req: Request | None) -> dict | None:
    """Return active profile session payload from signed cookie registry."""
    if not ENABLE_PROFILE_LOGIN or req is None:
        return None
    try:
        token = (req.cookies.get(SESSION_COOKIE_NAME) or "").strip()
        if not token:
            return None
        row = _PROFILE_SESSIONS.get(token)
        if not row:
            return None
        now_ts = int(datetime.now(timezone.utc).timestamp())
        if int(row.get("exp", 0)) <= now_ts:
            _PROFILE_SESSIONS.pop(token, None)
            return None
        return row
    except Exception:
        return None


def _profile_session_actor(req: Request | None) -> str:
    data = _profile_session_data(req)
    if not data:
        return ""
    return _normalize_actor_identity(str(data.get("actor") or ""))


def _profile_session_role(req: Request | None) -> str:
    data = _profile_session_data(req)
    if not data:
        return ""
    role = str(data.get("role") or "").strip().lower()
    return role if role in {"admin", "adv"} else ""


def _api_key_values() -> list[str]:
    """Return configured machine-to-machine API keys."""
    values = _parse_secret_env("APP_API_KEYS")
    if not values:
        values = _parse_secret_env("N8N_API_KEY")
    return values


def _api_key_actor() -> str:
    actor = _normalize_actor_identity(os.environ.get("APP_API_ACTOR", "n8n"))
    return actor or "n8n"


def _api_key_role() -> str:
    role = (os.environ.get("APP_API_ROLE") or "adv").strip().lower()
    return role if role in {"admin", "adv"} else "adv"


def _extract_api_key(req: Request | None) -> str:
    """Extract machine API key from headers."""
    if req is None:
        return ""
    api_key = (req.headers.get("x-api-key") or "").strip()
    if api_key:
        return api_key
    auth = (req.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _api_key_authenticated(req: Request | None) -> bool:
    provided = _extract_api_key(req)
    if not provided:
        return False
    for expected in _api_key_values():
        if hmac.compare_digest(provided, expected):
            return True
    return False


def _extract_actor_from_request(req: Request | None) -> str:
    """Extract actor from trusted upstream headers only (no fallback)."""
    if req is None:
        return ""
    candidates: list[str] = []
    for hk in (
        "x-forwarded-user",
        "x-forwarded-preferred-username",
        "x-forwarded-username",
        "x-forwarded-email",
        "x-forwarded-sub",
        "x-auth-request-user",
        "x-auth-request-email",
        "x-auth-request-preferred-username",
        "x-ms-client-principal-name",
        "x-ms-client-principal-idp",
        "x-databricks-user",
        "x-user-email",
        "x-remote-user",
        "remote-user",
        "x-end-user",
        "x-user",
    ):
        hv = (req.headers.get(hk) or "").strip()
        if hv:
            candidates.append(hv)

    for raw in candidates:
        value = raw.strip().strip('"').strip("'")
        if not value:
            continue
        lower = value.lower()
        if "@" in value:
            for token in value.replace(";", ",").replace(" ", ",").split(","):
                token = token.strip().strip('"').strip("'")
                if token and "@" in token:
                    return token.lower()
        if "/" in value:
            tail = value.split("/")[-1].strip()
            if tail:
                return tail.lower()
        if lower.startswith("users:"):
            return lower.split(":", 1)[1].strip()
        if lower.startswith("user:"):
            return lower.split(":", 1)[1].strip()
        if lower:
            return lower
    return ""


def _resolve_actor(req: Request | None = None, payload: dict | None = None) -> str:
    """Resolve actor identity from payload, headers, then environment fallback."""
    p = payload or {}
    actor = (p.get("operator") or p.get("actor") or "").strip()
    if actor:
        return _normalize_actor_identity(actor)

    actor_session = _profile_session_actor(req)
    if actor_session:
        return actor_session

    actor_hdr = _extract_actor_from_request(req)
    if actor_hdr:
        return actor_hdr

    if _api_key_authenticated(req):
        return _api_key_actor()

    # Local dev: no SSO proxy injects headers, so fall back to DEV_ACTOR to
    # mirror the authenticated identity/role you would have on Databricks.
    if IS_LOCAL and DEV_ACTOR:
        return DEV_ACTOR

    default_actor = _normalize_actor_identity(os.environ.get("DEFAULT_APP_ACTOR", "operator"))
    if _APP_REQUIRE_AUTH:
        return ""
    return default_actor or "operator"


def _actor_folder_name(actor: str | None) -> str:
    """Normalize actor into a filesystem-safe folder name."""
    raw = (actor or "").strip().lower()
    if not raw:
        return "operator"
    raw = raw.replace("\\", "/").split("/")[-1]
    safe = "".join(ch if (ch.isalnum() or ch in ("-", "_", ".")) else "_" for ch in raw)
    safe = safe.strip("._-")
    return safe[:80] or "operator"


def _resolve_role(actor: str) -> str:
    """Resolve role with the 2-role model: admin or adv.

    Legacy vars APP_REVIEW_USERS / APP_READONLY_USERS are treated as adv.
    """
    a = _normalize_actor_identity(actor)
    db_role = _db_role_override(a)
    if db_role:
        return db_role
    if a in _parse_csv_env("APP_ADMIN_USERS"):
        return "admin"
    # Keep short-term backward compatibility for existing env configs.
    legacy_adv = _parse_csv_env("APP_REVIEW_USERS") | _parse_csv_env("APP_READONLY_USERS")
    if not a or a in legacy_adv:
        return "adv"
    return "adv"


def _resolve_role_for_request(actor: str, req: Request | None = None) -> str:
    """Resolve role with request-aware profile session override."""
    session_role = _profile_session_role(req)
    if session_role:
        return session_role
    if _api_key_authenticated(req):
        return _api_key_role()
    return _resolve_role(actor)


def _ensure_can_mutate(req: Request | None = None, payload: dict | None = None) -> tuple[str, str]:
    """Return (actor, role) for mutation endpoints.

    In the current 2-role model, both admin and adv can mutate domain data.
    """
    actor = _resolve_actor(req, payload)
    role = _resolve_role_for_request(actor, req)
    return actor, role


def _ensure_admin(req: Request | None = None, payload: dict | None = None) -> tuple[str, str]:
    """Return (actor, role) and enforce admin-only endpoints."""
    actor, role = _ensure_can_mutate(req, payload)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return actor, role


# ── FILE2EDI engine conversion ─────────────────────────────────────────────────
def _file2edi_convert(pdf_path: Path) -> dict:
    """Primary: FILE2EDI FullCodeEngine + app/edifact_generator.build_orders_d96a."""
    result = {"ok": False, "edifact": "", "po_number": "", "soldto": "",
              "shipto": "", "warnings": [], "structured": {}, "error": ""}
    try:
        from app.engine import FullCodeEngine
        from app.edifact_generator import build_order_from_extraction, build_orders_d96a

        engine = FullCodeEngine()
        resp   = engine.extract_pdf(
            pdf_path.read_bytes(), filename=pdf_path.name, pages="1-5",
        )
        merged: dict = {}
        for pg in resp.get("results") or []:
            merged.update((pg.get("fields") or {}).get("structured") or {})
        result["structured"] = merged

        order, errors = build_order_from_extraction(merged)
        if errors or order is None:
            result["error"] = ", ".join(errors) if errors else "extraction returned None"
            return result

        iref = str(uuid.uuid4())[:8].upper()
        edifact, warnings = build_orders_d96a(order, iref)
        result.update(ok=True, edifact=edifact, po_number=order.po_number,
                      soldto=order.buyer.sap_code, shipto=order.ship_to.sap_code,
                      warnings=warnings)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _legacy_convert(pdf_path: Path) -> dict:
    """Fallback: src/engine_adapter.process_pdf_to_edifact."""
    try:
        from src.engine_adapter import process_pdf_to_edifact
        r = process_pdf_to_edifact(pdf_path)
        if r.status == "COMPLETED":
            return {"ok": True, "edifact": r.output_content or "",
                    "po_number": r.po_number or "", "soldto": r.soldto or "",
                    "shipto": "", "warnings": [], "tst_filename": r.output_filename or ""}
        return {"ok": False, "error": r.rejection_reason or "REJECTED",
                "po_number": r.po_number or ""}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _extract_pdf_text(pdf_path: Path) -> tuple[str, str]:
    """Multi-engine text extraction (pdfplumber → fitz → pypdf)."""
    for fn, name in [
        (lambda p: __import__("pdfplumber").open(str(p)).pages,
         "pdfplumber"),
    ]:
        try:
            import pdfplumber
            with pdfplumber.open(str(pdf_path)) as pdf:
                text = "\n".join(pg.extract_text() or "" for pg in pdf.pages).strip()
            if len(text) >= 80:
                return text, "pdfplumber"
        except Exception:
            pass
    try:
        import fitz
        doc  = fitz.open(str(pdf_path))
        text = "\n".join(p.get_text() for p in doc).strip()
        doc.close()
        if len(text) >= 80:
            return text, "fitz"
    except Exception:
        pass
    try:
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader
        reader = PdfReader(str(pdf_path))
        text   = "\n".join(p.extract_text() or "" for p in reader.pages).strip()
        if text:
            return text, "pypdf"
    except Exception:
        pass
    return "", "none"


# ── History ────────────────────────────────────────────────────────────────────
def _load_history() -> list[list]:
    try:
        if not os.path.exists(DB_PATH):
            return []
        conn = sqlite3.connect(DB_PATH, timeout=5)
        try:
            rows = conn.execute(
                "SELECT id,filename,status,po_number,sold_to,ship_to,created_at,rejection_reason "
                "FROM jobs ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        except sqlite3.OperationalError:
            try:
                # Standalone schema variant (src/database.py): source_filename + soldto
                rows = conn.execute(
                    "SELECT id,source_filename,status,po_number,soldto,'' as ship_to,created_at,rejection_reason "
                    "FROM jobs ORDER BY created_at DESC LIMIT 100"
                ).fetchall()
            except Exception:
                try:
                    rows = conn.execute(
                        "SELECT correlation_id,source_filename,status,order_key,'','',created_at,rejection_code "
                        "FROM order_ledger ORDER BY created_at DESC LIMIT 100"
                    ).fetchall()
                except Exception:
                    rows = []
        conn.close()
        return [list(r) for r in rows]
    except Exception as exc:
        log.warning("History load error: %s", exc)
        return []


# ── Master data helpers ────────────────────────────────────────────────────────
_MASTER_FILES = [
    "10564_Customers.csv", "10564_Partners.csv",
    "10564_Materials.csv", "DB_Salesorder.csv",
]


def _download_workspace_file(ws_path: str, dst_path: Path) -> None:
    """Download a single workspace file via the Databricks REST API.

    Inside Databricks Apps containers the /Workspace FUSE mount is not
    available, so we fall back to the HTTP export endpoint which works
    on every platform as long as the app SP has CAN_READ on the file.

    Uses ``direct_download=true`` to stream raw bytes — no base64, no
    10 MB limit.
    """
    import requests as _req

    host = DATABRICKS_HOST.rstrip("/")
    if not host.startswith("http"):
        host = f"https://{host}"
    encoded = urllib.parse.quote(ws_path, safe="")
    url = (f"{host}/api/2.0/workspace/export"
           f"?path={encoded}&format=AUTO&direct_download=true")
    headers = {k: v for k, v in _auth_headers().items()
               if not k.startswith("_")}  # drop error keys
    resp = _req.get(url, headers=headers, timeout=120, stream=True)
    resp.raise_for_status()
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dst_path, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=65_536):
            fh.write(chunk)


def _masterdata_stats() -> dict:
    """Return rich per-file status dict using in-memory cache (Req 3).
    Falls back to a quick disk check if cache is empty (startup race condition).
    """
    result: dict[str, dict] = {}
    for key, fname in _MD_FILES.items():
        entry = MASTERDATA_CACHE.get(key)
        if entry and (entry.get("rows", 0) > 0 or entry.get("error")):
            # Status derivation from cache
            if entry.get("error") and not entry.get("rows", 0):
                status = "ERROR"
            elif entry.get("rows", 0) == 0:
                status = "EMPTY"
            elif entry.get("schema_valid") is False:
                status = "SCHEMA_INVALID"
            else:
                status = "OK"
            result[key] = {
                "file":             fname,
                "status":           status,
                "rows":             entry.get("rows", 0),
                "required_columns": entry.get("required_columns", _MD_REQUIRED_COLS.get(key, [])),
                "present_columns":  entry.get("present_columns", []),
                "missing_columns":  entry.get("missing_columns", []),
                "source":           entry.get("source", "bundled"),
                "loaded_at":        entry.get("loaded_at"),
                "file_size_kb":     entry.get("file_size_kb", 0.0),
                "schema_valid":     entry.get("schema_valid"),
                "warnings":         entry.get("warnings", []),
            }
        else:
            # Disk fallback (cache not yet loaded)
            fp = Path(MASTER_DATA_RUNTIME) / fname
            if not fp.exists():
                result[key] = {
                    "file": fname, "status": "MISSING", "rows": 0,
                    "required_columns": _MD_REQUIRED_COLS.get(key, []),
                    "present_columns": [], "missing_columns": _MD_REQUIRED_COLS.get(key, []),
                    "source": "error", "loaded_at": None, "file_size_kb": 0.0,
                    "schema_valid": False,
                    "warnings": [f"Fichier introuvable: {fp}"],
                }
            else:
                try:
                    with open(fp, encoding="utf-8-sig", errors="replace") as fh:
                        n = sum(1 for _ in fh) - 1
                    result[key] = {
                        "file": fname, "status": "OK" if n > 0 else "EMPTY",
                        "rows": max(0, n),
                        "required_columns": _MD_REQUIRED_COLS.get(key, []),
                        "present_columns": [], "missing_columns": [],
                        "source": "bundled", "loaded_at": None,
                        "file_size_kb": round(fp.stat().st_size / 1024, 1),
                        "schema_valid": None,
                        "warnings": ["Cache non chargé — rechargement recommandé."],
                    }
                except Exception as exc:
                    result[key] = {
                        "file": fname, "status": "ERROR", "rows": 0,
                        "required_columns": _MD_REQUIRED_COLS.get(key, []),
                        "present_columns": [], "missing_columns": [],
                        "source": "error", "loaded_at": None, "file_size_kb": 0.0,
                        "schema_valid": False, "warnings": [str(exc)],
                    }
    return result


def _sync_masterdata() -> list[list]:
    """Copy master data CSVs from source to runtime directory.

    Two modes:
    - Filesystem copy: local path, /Workspace mounted path, or /Volumes UC path → shutil.copy2
    - Databricks Workspace API export fallback: only for /Workspace/* when FUSE is not mounted
    """
    rows = []
    src = Path(MASTER_DATA_SRC)
    dst = Path(MASTER_DATA_RUNTIME)
    dst.mkdir(parents=True, exist_ok=True)

    first_source_file = src / _MASTER_FILES[0]
    src_str = MASTER_DATA_SRC.strip()
    is_workspace_path = src_str.startswith("/Workspace/")

    # Use Workspace export API only for /Workspace paths when FUSE is unavailable.
    # UC Volumes (/Volumes/...) must be accessed as regular filesystem paths.
    use_api = is_workspace_path and not first_source_file.exists()
    log.info("masterdata sync: mode=%s src=%s dst=%s",
             "api" if use_api else "fs", src, dst)

    for fname in _MASTER_FILES:
        df = dst / fname
        try:
            if use_api:
                ws_path = f"{MASTER_DATA_SRC.rstrip('/')}/{fname}"
                _download_workspace_file(ws_path, df)
            else:
                shutil.copy2(str(src / fname), str(df))

            with open(df, encoding="utf-8-sig", errors="replace") as fh:
                n = sum(1 for _ in fh) - 1
            h = hashlib.sha256(df.read_bytes()).hexdigest()[:10]
            rows.append([fname, f"{max(0, n)} lignes", f"sha={h}", "OK"])
        except Exception as exc:
            exc_str = str(exc).lower()
            if "404" in exc_str or "not found" in exc_str:
                err_cat = "source introuvable (404)"
            elif "403" in exc_str or "forbidden" in exc_str:
                err_cat = "permission insuffisante (403)"
            elif "401" in exc_str or "unauthorized" in exc_str:
                err_cat = "non authentifié (401)"
            else:
                err_cat = str(exc)[:150]
            log.warning("masterdata sync failed for %s: %s", fname, exc)
            rows.append([fname, "—", "—", f"ERROR: {err_cat}"])

    # Invalidate in-memory masterdata cache so next PDF uses fresh data
    try:
        import app.masterdata as _md
        _md.master_data_cache = None
        _md.master_data_cache_fingerprint = None
    except Exception:
        pass

    return rows



# ── SFTP helper ────────────────────────────────────────────────────────────────
def _test_sftp() -> tuple[bool, str]:
    host = os.environ.get("SFTP_HOST", "")
    user = os.environ.get("SFTP_USERNAME", "")
    pwd  = os.environ.get("SFTP_PASSWORD", "")
    if not host:
        return False, "SFTP_HOST non configuré. .tst généré localement sans blocage."
    try:
        import paramiko
        t = paramiko.Transport((host, int(os.environ.get("SFTP_PORT","22"))))
        t.connect(username=user, password=pwd)
        sftp = paramiko.SFTPClient.from_transport(t)
        rdir = os.environ.get("SFTP_REMOTE_DIR",".")
        lst  = sftp.listdir(rdir)
        t.close()
        return True, f"Connecté à {host} en tant que {user} — {len(lst)} fichiers dans {rdir}"
    except Exception as exc:
        return False, f"Échec ({type(exc).__name__}): {exc}"


# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(title="EDIFACT Generator", version="4.0.0",
              docs_url="/api/docs", redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# Auth defaults to ON in Databricks (SSO proxy present) and OFF locally unless
# a DEV_ACTOR is provided, so `uvicorn server:app` just works on a dev machine.
_auth_default = "true" if (IS_DATABRICKS or DEV_ACTOR) else "false"
_APP_REQUIRE_AUTH = os.environ.get("APP_REQUIRE_AUTH", _auth_default).strip().lower() in {"1", "true", "yes", "on"}
_PUBLIC_API_PATHS = {
    "/api/health",
    "/api/health/system",
    "/api/proxy/health",
    "/api/auth/modes",
    "/api/auth/login",
    "/api/auth/logout",
    "/health",
    "/healthz",
}

if os.environ.get("APP_REVIEW_USERS") or os.environ.get("APP_READONLY_USERS"):
    log.warning("RBAC: APP_REVIEW_USERS / APP_READONLY_USERS are deprecated and now mapped to role=adv")


@app.middleware("http")
async def _require_authenticated_user(request: Request, call_next):
    """Enforce authenticated user for API routes when APP_REQUIRE_AUTH is enabled."""
    path = request.url.path or ""
    if _APP_REQUIRE_AUTH and path.startswith("/api/") and path not in _PUBLIC_API_PATHS:
        actor = _resolve_actor(request)
        if not actor:
            return JSONResponse(status_code=401, content={"detail": "Authentification requise"})
    return await call_next(request)


class ProfileLoginPayload(BaseModel):
    actor: str
    role: str


@app.get("/api/auth/modes")
def api_auth_modes():
    """Expose available login mechanisms for the login page."""
    return {
        "api_key_enabled": bool(_api_key_values()),
        "profile_login_enabled": ENABLE_PROFILE_LOGIN,
        "workspace_sso_available": True,
        "allowed_roles": ["admin", "adv"],
    }


@app.post("/api/auth/login")
def api_auth_login(payload: ProfileLoginPayload):
    """Create a profile session cookie (local/dev oriented)."""
    if not ENABLE_PROFILE_LOGIN:
        raise HTTPException(status_code=403, detail="Connexion par profil désactivée")

    actor = _normalize_actor_identity(payload.actor)
    role = (payload.role or "").strip().lower()
    if not actor:
        raise HTTPException(status_code=400, detail="Identifiant utilisateur requis")
    if role not in {"admin", "adv"}:
        raise HTTPException(status_code=400, detail="Rôle invalide (admin|adv)")

    token = uuid.uuid4().hex
    now_ts = int(datetime.now(timezone.utc).timestamp())
    _PROFILE_SESSIONS[token] = {
        "actor": actor,
        "role": role,
        "exp": now_ts + SESSION_TTL_SECONDS,
    }

    resp = JSONResponse({"ok": True, "actor": actor, "role": role})
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return resp


@app.post("/api/auth/logout")
def api_auth_logout(req: Request):
    token = (req.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    if token:
        _PROFILE_SESSIONS.pop(token, None)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return resp



# ── F2EDIV2 Proxy ─────────────────────────────────────────────────────────────

# ── Local F2EDIV2 engine ───────────────────────────────────────────────────────

class _LRUCache(OrderedDict):
    """LRU cache for idempotent PDF processing (keyed by SHA-256)."""
    def __init__(self, maxsize: int = 200):
        super().__init__()
        self.maxsize = maxsize

    def get_or_none(self, key: str):
        if key in self:
            self.move_to_end(key)
            return self[key]
        return None

    def put(self, key: str, value: dict) -> None:
        self[key] = value
        self.move_to_end(key)
        if len(self) > self.maxsize:
            self.popitem(last=False)


_f2edi_cache: _LRUCache = _LRUCache(maxsize=200)
_f2edi_requests_processed: int = 0


def _f2edi_build_raw_address(addr: dict) -> str:
    parts = [str(addr[k]).strip() for k in ("Nom", "Rue", "Code postal", "Ville")
             if addr.get(k) and str(addr[k]).strip()]
    return ", ".join(parts)


def _f2edi_build_response(structured: dict, filename: str,
                           pdf_hash: str, elapsed: float,
                           cached: bool = False) -> dict:
    """Map structured extraction result to the unified API response shape."""
    doc    = structured.get("document", {})
    adr    = structured.get("adresses", {}).get("Adresse de livraison validee", {})
    det    = structured.get("adresses", {}).get("Adresse de livraison detectee", {})
    rej    = structured.get("rejets", {})
    edi    = structured.get("edifact", {})
    lignes = structured.get("lignes_commande", {})
    return {
        "status": "OK",
        "filename": filename,
        "pdf_hash": pdf_hash,
        "cached": cached,
        "processing_time_s": round(elapsed, 1),
        "order": {
            "po_number":     doc.get("Numero de commande"),
            "order_date":    doc.get("Date commande LLM"),
            "delivery_date": doc.get("Date livraison souhaitee"),
        },
        "customer": {
            "soldto":    adr.get("SOLDTO"),
            "shipto":    adr.get("SHIPTO"),
            "name":      adr.get("Nom"),
            "confidence": adr.get("Confiance", 0),
            "soldto_confidence": 90 if adr.get("SOLDTO") != adr.get("SHIPTO")
                                    else adr.get("Confiance", 0),
            "shipto_confidence": adr.get("Confiance", 0),
            "shipto_score":      adr.get("shipto_score", 0),
            "scoring_decision":  adr.get("scoring_decision", ""),
            "disambiguation":    adr.get("Disambiguation", ""),
            "disambiguation_explanation": adr.get("Disambiguation_explanation", ""),
            "reason_codes":  adr.get("reason_codes", []),
            "matched_by":    adr.get("matched_by", []),
            "delivery_address": {
                "street":      adr.get("Rue") or adr.get("Adresse", ""),
                "postal_code": adr.get("Code postal", ""),
                "city":        adr.get("Ville", ""),
                "country":     "FR",
            },
            "detected_address": {
                "name":        det.get("Nom", "")        or adr.get("Nom", "")        or "",
                "street":      det.get("Rue", "")        or adr.get("Rue", "")        or "",
                "postal_code": det.get("Code postal", "") or adr.get("Code postal", "") or "",
                "city":        det.get("Ville", "")      or adr.get("Ville", "")      or "",
                "raw":         det.get("Adresse complete", "") or _f2edi_build_raw_address(det)
                               or _f2edi_build_raw_address(adr),
                "statut":      det.get("Statut", "") if (det.get("Rue") or det.get("Code postal"))
                               else (adr.get("Disambiguation", "") or det.get("Statut", "")),
            },
        },
        "lines": {
            "count": lignes.get("nb_lignes", 0),
            "items": lignes.get("lignes", []),
        },
        "rejection": {
            "decision":       rej.get("decision"),
            "reason":         rej.get("primary_reason"),
            "blocking_count": rej.get("blocking_count", 0),
            "warning_count":  rej.get("warning_count", 0),
            "details":        rej.get("rejections", []),
        },
        "edifact": {
            "generated": edi.get("generated", False),
            "message":   edi.get("message"),
            "warnings":  edi.get("warnings", []),
            "errors":    edi.get("errors"),
        },
        "error": None,
    }


def _local_process_and_respond(payload: bytes, filename: str, actor: str | None = None) -> dict:
    """Run the full F2EDIV2 pipeline locally. Idempotent via SHA-256 cache."""
    global _f2edi_requests_processed
    import time as _t
    pdf_hash = hashlib.sha256(payload).hexdigest()
    stored_pdf_path = _persist_uploaded_pdf(payload, filename, pdf_hash, actor=actor)

    # Idempotency cache
    hit = _f2edi_cache.get_or_none(pdf_hash)
    if hit is not None:
        r = hit.copy()
        r["cached"] = True
        r["processing_time_s"] = 0.0
        if stored_pdf_path:
            r["pdf_storage_path"] = stored_pdf_path
        return r

    t0 = _t.time()
    try:
        from app.pdf_reader import pdf_pages_to_text
        from app.extraction import extract_candidate_fields
        pages = pdf_pages_to_text(payload, "1")
        if not pages:
            raise ValueError("Impossible d'extraire le texte du PDF")
        text   = pages[0]["text"]
        layout = pages[0].get("layout")
        fields = extract_candidate_fields(text, "", filename, layout, {})
        structured = fields.get("structured", {})
        response = _f2edi_build_response(structured, filename, pdf_hash, _t.time() - t0)
    except Exception as exc:
        log.exception("_local_process_and_respond failed for %s", filename)
        elapsed = round(_t.time() - t0, 1)
        response = {
            "status": "ERROR", "filename": filename, "pdf_hash": pdf_hash,
            "cached": False, "processing_time_s": elapsed,
            "order":   {"po_number": None, "order_date": None, "delivery_date": None},
            "customer": {
                "soldto": None, "shipto": None, "name": None, "confidence": 0,
                "delivery_address": {"street": "", "postal_code": "", "city": "", "country": ""},
                "detected_address": {"name": "", "street": "", "postal_code": "", "city": "", "raw": ""},
            },
            "lines":     {"count": 0, "items": []},
            "rejection": {
                "decision": "REJECTED", "reason": "PDF_PARSE_FAILURE",
                "blocking_count": 1, "warning_count": 0,
                "details": [{"code": "PDF_PARSE_FAILURE", "message": str(exc),
                              "severity": "blocking", "details": {}}],
            },
            "edifact":   {"generated": False, "message": None, "warnings": [], "errors": None},
            "error": str(exc),
        }

    if response["status"] == "OK":
        _f2edi_cache.put(pdf_hash, response.copy())
    if stored_pdf_path:
        response["pdf_storage_path"] = stored_pdf_path
    _f2edi_requests_processed += 1
    return response


def _persist_uploaded_pdf(
    payload: bytes,
    filename: str,
    pdf_hash: Optional[str] = None,
    actor: str | None = None,
) -> Optional[str]:
    """Persist uploaded PDF payload to configured storage for traceability."""
    if not payload:
        return None
    try:
        original = Path(filename or "commande.pdf").name
        stem = Path(original).stem or "document"
        safe_stem = "".join(ch if (ch.isalnum() or ch in ("-", "_")) else "_" for ch in stem)[:80]
        if not safe_stem:
            safe_stem = "document"
        digest = pdf_hash or hashlib.sha256(payload).hexdigest()
        stamp = _datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        actor_dir = Path(PDF_STORAGE_DIR) / _actor_folder_name(actor)
        actor_dir.mkdir(parents=True, exist_ok=True)
        target = actor_dir / f"{stamp}_{digest[:12]}_{safe_stem}.pdf"
        target.write_bytes(payload)
        return str(target)
    except Exception as exc:
        log.warning("_persist_uploaded_pdf(%s): %s", filename, exc)
        return None


def _store_conversion_history(result: dict) -> None:
    """Persist conversion result in local SQLite history."""
    if not os.path.exists(DB_PATH):
        return
    try:
        decision  = result.get("rejection", {}).get("decision") or "UNKNOWN"
        po_number = result.get("order", {}).get("po_number") or ""
        sold_to   = result.get("customer", {}).get("soldto") or ""
        ship_to   = result.get("customer", {}).get("shipto") or ""
        filename  = result.get("filename") or ""
        reason    = result.get("rejection", {}).get("reason") or ""
        row_id    = result.get("pdf_hash") or str(uuid.uuid4())
        conn = sqlite3.connect(DB_PATH, timeout=5)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO jobs "
                "(id, filename, status, po_number, sold_to, ship_to, created_at, rejection_reason) "
                "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?)",
                [row_id, filename, decision, po_number, sold_to, ship_to, reason],
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()
    except Exception as exc:
        log.warning("_store_conversion_history: %s", exc)


@app.get("/api/proxy/health")
def api_proxy_health():
    """Health check — fully local.  Always returns top-level ok/status (Issue 1 fix)."""
    local_md  = _masterdata_stats()   # dict after masterdata refactoring
    mc_status = {k: {"rows": v.get("rows",0), "loaded_at": v.get("loaded_at")}
                 for k, v in MASTERDATA_CACHE.items()}
    # Fix: iterate dict values, not dict keys (md_ok bug)
    md_rows_ok   = all(v.get("rows", 0) > 0 for v in local_md.values()) if local_md else False
    md_schema_ok = all(v.get("schema_valid", True) is not False
                       for v in local_md.values()) if local_md else True
    db_ok = True
    try:
        import sqlite3 as _sq2
        _c = _sq2.connect(DB_PATH, timeout=1)
        _c.execute("SELECT 1").fetchone()
        _c.close()
    except Exception:
        db_ok = False
    storage = get_storage_mode()
    return {
        # ── Top-level contract (required by frontend) ───────────────────────
        "ok":     True,
        "status": "ok",
        # ── Structured sections ─────────────────────────────────────────────
        "api":      {"ok": True, "status": "ok", "version": "2.1.0"},
        "database": {"ok": db_ok, "status": "ok" if db_ok else "ERROR",
                     "backend": storage.get("backend", "sqlite")},
        "masterdata": {"ok": md_rows_ok, "schema_ok": md_schema_ok},
        "profile": {
            "name": "ELM_STANDARD", "syntax": "UNOC:3", "message": "ORDERS D.96A",
            "sender_gln": UNB_SENDER_GLN, "receiver_gln": UNB_RECEIVER_GLN,
            "locked": True,
        },
        "storage_mode": storage,
        # ── Legacy flat fields (backward compat) ───────────────────────────
        "local":           {"status": "ok", "profile": "ELM_STANDARD",
                            "sender_gln": UNB_SENDER_GLN, "receiver_gln": UNB_RECEIVER_GLN},
        "db_ok":           db_ok,
        "sftp_configured": bool(os.environ.get("SFTP_HOST", "")),
        "f2edi_base":      "local",
        "mc_status":       mc_status,
    }



@app.post("/api/proxy/convert-batch")
async def api_proxy_convert_batch(req: Request, files: list[UploadFile] = File(...), callback_url: str = Form("")):
    """Process multiple PDFs sequentially.  Max 20 files per batch (Issue 5)."""
    MAX_BATCH = 20
    actor = _resolve_actor(req)
    if not files:
        return JSONResponse(status_code=400, content={"error": "Aucun fichier reçu"})
    if len(files) > MAX_BATCH:
        return JSONResponse(status_code=400,
            content={"error": f"Maximum {MAX_BATCH} fichiers PDF par lot",
                     "count": len(files)})
    results = []
    safe_callback_url = _sanitize_callback_url(callback_url)
    for f in files:
        fname = f.filename or "commande.pdf"
        try:
            payload = await f.read()
            if not payload:
                results.append({"filename": fname, "status": "ERROR", "error": "Fichier vide"})
                continue
            if not fname.lower().endswith(".pdf"):
                results.append({"filename": fname, "status": "ERROR",
                                 "error": "Seuls les fichiers PDF sont acceptés"})
                continue
            if len(payload) > 20 * 1024 * 1024:
                results.append({"filename": fname, "status": "ERROR",
                                 "error": "Fichier trop volumineux (max 20 Mo)"})
                continue
            result = _local_process_and_respond(payload, fname, actor=actor)
            try:
                _init_db()
                _upsert_conversion(result, callback_url=safe_callback_url)
                _add_audit(result.get("pdf_hash", "?"), "conversion_created", actor,
                           {"filename": result.get("filename"), "batch": True})
                _emit_conversion_callback(result.get("pdf_hash", "?"), "conversion_created", actor,
                                          {"filename": result.get("filename"), "batch": True})
            except Exception:
                pass
            results.append(result)
        except Exception as exc:
            log.warning("batch convert failed for %s: %s", fname, exc)
            results.append({"filename": fname, "status": "FAILED", "error": str(exc)[:200]})
    return {"batch_size": len(files), "results": results}


@app.get("/health")
@app.get("/api/health")
@app.get("/api/health/system")
def api_health_alias():
    """Alias for /api/proxy/health — satisfies health checks and legacy frontend calls."""
    return api_proxy_health()


@app.get("/api/me")
def api_me(req: Request):
    """Return resolved actor + role for profile-aware UI routing."""
    actor = _resolve_actor(req)
    authenticated = (not _APP_REQUIRE_AUTH) or bool(actor)
    return {
        "actor": actor,
        "role": _resolve_role_for_request(actor, req),
        "authenticated": authenticated,
    }


@app.get("/api/me/debug")
def api_me_debug(req: Request):
    """Diagnostic: show raw SSO headers, resolved actor, and role chain.
    Useful to confirm which header Databricks injects and why a role is resolved.
    """
    actor = _resolve_actor(req)
    session_role = _profile_session_role(req)
    db_role = _db_role_override(actor) if actor else None
    admin_set = list(_parse_csv_env("APP_ADMIN_USERS"))
    # Collect relevant auth headers (values truncated for safety)
    auth_headers = {}
    for hk in (
        "x-forwarded-user", "x-forwarded-email", "x-forwarded-preferred-username",
        "x-forwarded-username", "x-databricks-user", "x-auth-request-user",
        "x-auth-request-email", "x-ms-client-principal-name", "x-user-email",
        "x-remote-user", "remote-user", "x-end-user", "x-user",
    ):
        v = req.headers.get(hk, "")
        if v:
            auth_headers[hk] = v[:80]
    return {
        "actor": actor,
        "role": _resolve_role_for_request(actor, req),
        "role_source": "session" if session_role else ("api_key" if _api_key_authenticated(req) else ("db_override" if db_role else "env_match" if actor in _parse_csv_env("APP_ADMIN_USERS") else "default_adv")),
        "session_role": session_role or None,
        "api_key_authenticated": _api_key_authenticated(req),
        "db_role": db_role,
        "in_admin_users": actor in _parse_csv_env("APP_ADMIN_USERS"),
        "admin_users_set": admin_set,
        "auth_headers_received": auth_headers,
        "is_databricks": IS_DATABRICKS,
        "require_auth": _APP_REQUIRE_AUTH,
        "profile_login_enabled": ENABLE_PROFILE_LOGIN,
    }


@app.post("/api/proxy/convert")
async def api_proxy_convert(req: Request, file: UploadFile = File(...), callback_url: str = Form("")):
    """Run the local F2EDIV2 engine on an uploaded PDF."""
    actor = _resolve_actor(req)
    payload = await file.read()
    if not payload:
        return JSONResponse(status_code=400,
            content={"status": "ERROR", "error": "Fichier vide"})
    if not (file.filename or "").lower().endswith(".pdf"):
        return JSONResponse(status_code=400,
            content={"status": "ERROR", "error": "Seuls les fichiers PDF sont acceptés"})
    result = _local_process_and_respond(payload, file.filename or "commande.pdf", actor=actor)
    safe_callback_url = _sanitize_callback_url(callback_url)
    try:
        _init_db()
        _upsert_conversion(result, callback_url=safe_callback_url)
        _add_audit(result.get("pdf_hash","?"), "conversion_created", actor,
                   {"filename": result.get("filename"), "decision": result.get("rejection",{}).get("decision")})
        _emit_conversion_callback(result.get("pdf_hash", "?"), "conversion_created", actor,
                                  {"filename": result.get("filename"),
                                   "decision": result.get("rejection", {}).get("decision")})
    except Exception:
        pass
    return result


# ── Startup: auto-sync master data ───────────────────────────────────────────
@app.on_event("startup")
async def _startup_sync_masterdata() -> None:
    """Ensure master data CSVs are available at boot, then init persistence + File2EDI schema.

    Masterdata strategy (in order):
    1. If all files already present in the runtime dir (bundled with snapshot) → use them.
    2. Otherwise, attempt API download from MASTER_DATA_SRC.
    Persistence strategy: Delta > Workspace JSONL > SQLite (auto-detected).
    File2EDI order tables: SQLite schema in data/file2edi_schema.sql.
    Non-blocking: failures are logged but never prevent the app from starting.
    """
    # ── File2EDI SQLite schema ────────────────────────────────────────────
    try:
        from src.file2edi.store import get_store
        get_store()  # initializes file2edi_* tables
        log.info("startup file2edi: order schema ready")
    except Exception as exc:
        log.warning("startup file2edi schema: %s", exc)
    # ── Masterdata ────────────────────────────────────────────────────────
    try:
        dst = Path(MASTER_DATA_RUNTIME)
        all_present = all((dst / f).exists() for f in _MASTER_FILES)
        if all_present:
            total = sum((dst / f).stat().st_size for f in _MASTER_FILES)
            _load_masterdata_cache()
            log.info("startup masterdata: all %d files already present (%.1f MB bundled) — skipping API sync",
                     len(_MASTER_FILES), total / 1_048_576)
        else:
            # Files missing — try API download
            rows = _sync_masterdata()
            _load_masterdata_cache()   # warm up cache after download
            ok  = sum(1 for r in rows if r[-1] == "OK")
            log.info("startup masterdata sync: %d/%d files OK", ok, len(rows))
            for r in rows:
                log.info("  %s → %s", r[0], r[-1])
    except Exception as exc:
        log.warning("startup masterdata sync failed (non-fatal): %s", exc)

    # ── Persistence backend (always runs — no early return above) ─────────
    try:
        _detect_and_init_backend()
        _maybe_migrate_sqlite_to_backend()
        log.info("persistence: backend=%s persistent=%s location=%s",
                 _PERSIST_BACKEND.get("backend"), _PERSIST_BACKEND.get("persistent"),
                 _PERSIST_BACKEND.get("location"))
    except Exception as _pe:
        log.warning("persistence backend init failed (SQLite fallback active): %s", _pe)


# ── Health ─────────────────────────────────────────────────────────────────────
@app.get("/healthz")
def healthz():
    return {"status": "ok", "profile": "ELM_STANDARD", "app": "edifact-generator"}


# ── Convert ────────────────────────────────────────────────────────────────────
@app.post("/api/convert")
async def api_convert(
    req: Request,
    file: UploadFile = File(...),
    send_sftp: str = Form("false"),
):
    actor = _resolve_actor(req)
    payload = await file.read()
    stored_pdf_path = _persist_uploaded_pdf(payload, file.filename or "order.pdf", actor=actor)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(payload)
        tmp_path = Path(tmp.name)

    corr_id = str(uuid.uuid4())[:8]
    try:
        # Text extraction for preview
        pdf_text, text_method = _extract_pdf_text(tmp_path)
        text_preview = (
            f"[{text_method} | {len(pdf_text):,} chars]\n\n"
            + pdf_text[:2000]
            + ("\n..." if len(pdf_text) > 2000 else "")
        ) if pdf_text else "[Aucun texte extrait]"

        # Primary: FILE2EDI
        f2e = _file2edi_convert(tmp_path)
        if f2e["ok"]:
            tst_content  = f2e["edifact"]
            tst_filename = Path(file.filename or "order.pdf").stem + ".tst"
            # Write to outbox
            outbox_path = Path(OUTBOX_DIR) / tst_filename
            outbox_path.write_text(tst_content, encoding="utf-8")
            # SFTP optional
            sftp_note = ""
            if send_sftp.lower() in ("true", "1"):
                try:
                    from src.sftp_delivery import SftpDelivery
                    from src.config_loader  import load_config
                    SftpDelivery(load_config(CONFIG_INI)).deliver(str(outbox_path))
                    sftp_note = " (SFTP envoyé)"
                except Exception as e:
                    sftp_note = f" (SFTP erreur: {e})"
            # Structural validation
            try:
                from src.edifact_validator import validate_edifact
                vr       = validate_edifact(tst_content)
                val_note = "" if vr.valid else f" [WARN: {','.join(vr.codes[:3])}]"
            except Exception:
                val_note = ""

            return JSONResponse({
                "ok": True,
                "status": f"[OK/FILE2EDI] {tst_filename} | SOLDTO {f2e['soldto']} | SHIPTO {f2e['shipto']}{sftp_note}{val_note}",
                "tst_filename": tst_filename,
                "po_number": f2e["po_number"],
                "soldto": f2e["soldto"],
                "shipto": f2e["shipto"],
                "warnings": f2e["warnings"],
                "edifact_preview": tst_content,
                "pdf_text_preview": text_preview,
                "text_method": text_method,
                "correlation_id": corr_id,
                "pdf_storage_path": stored_pdf_path,
                "rejection_reason": "",
            })

        # Fallback: legacy adapter
        leg = _legacy_convert(tmp_path)
        if leg["ok"]:
            tst_content  = leg["edifact"]
            tst_filename = Path(file.filename or "order.pdf").stem + ".tst"
            Path(OUTBOX_DIR, tst_filename).write_text(tst_content, encoding="utf-8")
            return JSONResponse({
                "ok": True,
                "status": f"[OK/legacy] {tst_filename} | PO {leg['po_number']} | file2edi: {f2e['error']}",
                "tst_filename": tst_filename,
                "po_number": leg["po_number"],
                "soldto": leg.get("soldto",""),
                "shipto": "",
                "warnings": [],
                "edifact_preview": tst_content,
                "pdf_text_preview": text_preview,
                "text_method": text_method,
                "correlation_id": corr_id,
                "pdf_storage_path": stored_pdf_path,
                "rejection_reason": "",
            })

        return JSONResponse({
            "ok": False,
            "status": f"[REJETÉ] {leg.get('error') or f2e['error']}",
            "tst_filename": "",
            "po_number": leg.get("po_number",""),
            "soldto": "", "shipto": "", "warnings": [],
            "edifact_preview": "",
            "pdf_text_preview": text_preview,
            "text_method": text_method,
            "correlation_id": corr_id,
            "pdf_storage_path": stored_pdf_path,
            "rejection_reason": leg.get("error") or f2e.get("error",""),
        })

    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass


# ── Validate EDIFACT ───────────────────────────────────────────────────────────
class ValidateRequest(BaseModel):
    edifact: str

@app.post("/api/validate")
def api_validate(req: ValidateRequest):
    report_parts = []
    try:
        from src.edifact_validator import validate_edifact
        vr = validate_edifact(req.edifact)
        if vr.valid:
            report_parts.append("Structural check: PASS")
        else:
            report_parts.append(f"Structural check: FAIL\nCodes: {', '.join(vr.codes)}")
            report_parts.extend(f"  · {d}" for d in vr.details)
    except Exception as exc:
        report_parts.append(f"Structural check skipped: {exc}")
    return {"report": "\n".join(report_parts), "ok": not any("FAIL" in p for p in report_parts)}


# ── AI Extract ─────────────────────────────────────────────────────────────────
class ExtractTextRequest(BaseModel):
    text: str = ""

@app.post("/api/extract")
async def api_extract(
    req: Request,
    file: Optional[UploadFile] = File(None),
    request: Optional[ExtractTextRequest] = None,
):
    # PDF path takes priority
    if file is not None:
        actor = _resolve_actor(req)
        payload = await file.read()
        stored_pdf_path = _persist_uploaded_pdf(payload, file.filename or "order.pdf", actor=actor)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(payload)
            tmp_path = Path(tmp.name)
        try:
            f2e = _file2edi_convert(tmp_path)
            return JSONResponse({
                "ok": True,
                "result": f2e["structured"],
                "status": f"FILE2EDI FullCodeEngine | PO {f2e.get('po_number','?')} | SOLDTO {f2e.get('soldto','?')}",
                "pdf_storage_path": stored_pdf_path,
            })
        finally:
            try:
                tmp_path.unlink()
            except Exception:
                pass

    # Text fallback — mlflow.deployments LLM (auth-portable inside Databricks Apps)
    text = (request.text if request else "") or ""
    if not text.strip():
        return JSONResponse({"ok": False, "result": {}, "status": "Texte vide"})

    from src.llm_client import llm_extract_json
    _system = (
        "Vous êtes un extracteur de commandes B2B pour Bosch France. "
        "Retournez UNIQUEMENT un JSON avec les clés: order_key, document_date, "
        "buyer_vat, shipto_address, shipto_postal, shipto_city, "
        "line_items[], confidence. Strict JSON, sans markdown."
    )
    try:
        result = llm_extract_json(
            prompt=f"TEXTE:\n\n{text[:5000]}",
            system=_system,
            max_tokens=1200,
        )
        if result is None:
            return JSONResponse({"ok": False, "result": {}, "status": "LLM unavailable or JSON parse error"})
        return JSONResponse({"ok": True, "result": result, "status": "LLM OK (mlflow.deployments)"})
    except Exception as exc:
        return JSONResponse({"ok": False, "result": {}, "status": str(exc)})


# ── History ────────────────────────────────────────────────────────────────────
@app.get("/api/history")
def api_history():
    return {"rows": _load_history()}


# ── Master data ────────────────────────────────────────────────────────────────
@app.get("/api/diagnostics/self-test")
def api_self_test():
    """Quick self-test of all subsystems.  Returns per-subsystem ok/error flags (Issue 6)."""
    tests: dict = {"api": True}
    # Settings
    try:
        api_settings(); tests["settings"] = True
    except Exception as exc:
        tests["settings"] = False; tests["settings_error"] = str(exc)[:100]
    # Masterdata stats
    try:
        stats = _masterdata_stats()
        tests["masterdata_stats"]  = True
        tests["masterdata_loaded"] = all(v.get("rows", 0) > 0 for v in stats.values())
        tests["masterdata_schema"] = all(v.get("schema_valid", True) is not False
                                         for v in stats.values())
    except Exception as exc:
        tests["masterdata_stats"] = False; tests["masterdata_error"] = str(exc)[:100]
    # Storage
    try:
        sm = get_storage_mode()
        tests["storage"]         = True
        tests["storage_backend"] = sm.get("backend", "?")
        tests["storage_persistent"] = sm.get("persistent", False)
    except Exception as exc:
        tests["storage"] = False; tests["storage_error"] = str(exc)[:100]
    # Conversion engine
    try:
        from src.edifact_builder import build_orders_message as _bem
        tests["conversion_engine"] = True
    except Exception as exc:
        tests["conversion_engine"] = False; tests["engine_error"] = str(exc)[:100]
    # SFTP / Email
    tests["sftp"]  = "configured" if os.environ.get("SFTP_HOST")  else "not_configured"
    tests["email"] = "configured" if os.environ.get("SMTP_HOST")  else "copy_only"
    # Summary
    errors = [k for k, v in tests.items() if isinstance(v, bool) and not v]
    tests["errors"] = errors
    tests["ok"]     = len(errors) == 0
    return tests


@app.get("/api/masterdata/stats")
def api_md_stats():
    """Rich masterdata status (Req 3).  Response: {files:{...}, summary:{...}}."""
    stats = _masterdata_stats()
    all_valid  = all(v.get("schema_valid", True) is not False for v in stats.values())
    total_rows = sum(v.get("rows", 0) for v in stats.values())
    last_sync  = max(_MD_LAST_SYNC.values(), default=None) if _MD_LAST_SYNC else None
    return {
        "files": stats,
        "summary": {
            "all_valid":  all_valid,
            "total_rows": total_rows,
            "last_sync":  last_sync,
        },
        "full_load_warning": (
            "Les fichiers masterdata sont traités comme full-load. "
            "Aucune suppression automatique n'est exécutée par File2EDI."
        ),
    }


@app.post("/api/masterdata/sync")
def api_md_sync():
    """Sync masterdata from workspace source.
    Writes audit events.  On failure keeps current cache (Req 4+8).
    """
    import datetime as _dt
    save_audit_event("__masterdata__", "masterdata_sync_attempted", "system",
                     {"source": MASTER_DATA_SRC})
    rows = _sync_masterdata()
    ok_files  = [r[0] for r in rows if len(r) >= 4 and r[3] == "OK"]
    err_files = [r[0] for r in rows if len(r) >= 4 and r[3] != "OK"]
    if ok_files:
        # Mark synced keys as workspace-sourced BEFORE reloading the cache
        now_iso = _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        for key, fname in _MD_FILES.items():
            if fname in ok_files:
                _MD_LAST_SYNC[key] = now_iso
        _load_masterdata_cache()
        save_audit_event("__masterdata__", "masterdata_sync_succeeded", "system",
                         {"ok": ok_files, "errors": err_files})
        log.info("masterdata sync succeeded: %d/%d files", len(ok_files), len(rows))
    else:
        # All failed — keep existing cache (Tier C)
        save_audit_event("__masterdata__", "masterdata_sync_failed", "system",
                         {"errors": [r[3] for r in rows if len(r) >= 4]})
        log.warning("masterdata sync: all files failed — cache unchanged")
    return {
        "synced":         len(ok_files),
        "failed":         len(err_files),
        "files":          [{"file": r[0],
                             "status": r[3] if len(r) > 3 else "?",
                             "detail": r[1] if len(r) > 1 else ""}
                            for r in rows],
        "cache_reloaded": bool(ok_files),
        "message": (
            f"{len(ok_files)}/{len(rows)} fichiers synchronisés"
            + (f" — {len(err_files)} erreur(s)" if err_files else "")
        ),
    }

@app.post("/api/masterdata/delta")
def api_md_delta():
    try:
        from src.datatables import create_all_tables
        statuses = create_all_tables()
        return {"results": [[s.name, "OK" if s.success else "FAIL", s.message] for s in statuses]}
    except Exception as exc:
        return {"results": [["—", "ERROR", str(exc)]]}


# ── Settings ───────────────────────────────────────────────────────────────────
@app.get("/api/settings")
def api_settings():
    """Return complete settings shape (Issue 3 fix)."""
    sftp_host  = os.environ.get("SFTP_HOST", "")
    sftp_ok    = bool(sftp_host)
    email_ok   = bool(os.environ.get("SMTP_HOST", ""))
    # Mask SFTP host: show last 4 chars only
    _h = sftp_host
    masked_host = ("*" * max(0, len(_h) - 4) + _h[-4:]) if len(_h) > 4 else ("*" * len(_h))
    return {
        # ── Structured sections (Issue 3) ───────────────────────────────────
        "profile": {
            "name": "ELM_STANDARD", "syntax": "UNOC:3", "message": "ORDERS D.96A",
            "sender_gln": UNB_SENDER_GLN, "receiver_gln": UNB_RECEIVER_GLN,
            "locked": True,
        },
        "api": {
            "status": "ok", "base_url": "(local)", "version": "2.1.0",
            "health_endpoint":        "/api/proxy/health",
            "convert_endpoint":       "/api/proxy/convert",
            "convert_batch_endpoint": "/api/proxy/convert-batch",
            "model_endpoint":         MODEL_ENDPOINT,
        },
        "masterdata": _masterdata_stats(),
        "sftp": {
            "configured":  sftp_ok,
            "status":      "CONFIGURED" if sftp_ok else "NOT_CONFIGURED",
            "host":        masked_host if sftp_ok else "—",
            "remote_path": os.environ.get("SFTP_REMOTE_DIR", "—"),
            "last_error":  None,
        },
        "email": {
            "configured":        email_ok,
            "mode":              "smtp" if email_ok else "copy_only",
            "rejection_mailbox": "botrejet.Commandes@fr.bosch.com",
        },
        "storage_mode": get_storage_mode(),
        # ── Legacy flat fields (backward compat) ───────────────────────────
        "sftp_host":         os.environ.get("SFTP_HOST", "(non configuré)"),
        "sftp_username":     os.environ.get("SFTP_USERNAME", "(non configuré)"),
        "sftp_remote_dir":   os.environ.get("SFTP_REMOTE_DIR", "(non configuré)"),
        "sender_gln":        UNB_SENDER_GLN,
        "receiver_gln":      UNB_RECEIVER_GLN,
        "model_endpoint":    MODEL_ENDPOINT,
        "token_status":      "SET" if os.environ.get("DATABRICKS_TOKEN") else "NOT SET (OAuth)",
        "catalog":           os.environ.get("EDIFACT_CATALOG", "hive_metastore"),
        "schema":            os.environ.get("EDIFACT_SCHEMA", "edifact_generator"),
        "masterdata_source": MASTER_DATA_SRC,
        "masterdata_runtime":MASTER_DATA_RUNTIME,
        "outbox":            OUTBOX_DIR,
    }


class RoleUpsertPayload(BaseModel):
    actor: str
    role: str


@app.get("/api/admin/roles")
def api_admin_roles(req: Request):
    """List current RBAC assignments (DB overrides + env admins)."""
    _ensure_admin(req)
    _init_db()

    env_admins = sorted(_parse_csv_env("APP_ADMIN_USERS"))
    env_rows = {
        a: {
            "actor": a,
            "role": "admin",
            "source": "env",
            "is_active": True,
            "updated_at": None,
            "updated_by": "env",
        }
        for a in env_admins
    }

    db_rows: list[dict] = []
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT actor, role, is_active, updated_at, updated_by
            FROM user_roles
            WHERE is_active=1
            ORDER BY actor ASC
            """
        ).fetchall()
        conn.close()
        for r in rows:
            db_rows.append(
                {
                    "actor": str(r["actor"]),
                    "role": str(r["role"]),
                    "source": "db",
                    "is_active": bool(r["is_active"]),
                    "updated_at": r["updated_at"],
                    "updated_by": r["updated_by"] or "system",
                }
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lecture des rôles impossible: {exc}")

    # DB overrides take precedence in effective role display.
    merged: dict[str, dict] = dict(env_rows)
    for row in db_rows:
        merged[row["actor"]] = row

    items = []
    for actor_key in sorted(merged.keys()):
        row = merged[actor_key]
        items.append(
            {
                **row,
                "effective_role": _resolve_role(actor_key),
            }
        )

    return {
        "items": items,
        "env_admin_count": len(env_admins),
        "db_assignment_count": len(db_rows),
    }


@app.put("/api/admin/roles")
def api_admin_upsert_role(req: Request, payload: RoleUpsertPayload):
    """Create or update one RBAC assignment in DB (admin/adv)."""
    admin_actor, _ = _ensure_admin(req, payload.model_dump())
    _init_db()

    actor = _normalize_actor_identity(payload.actor)
    role = (payload.role or "").strip().lower()
    if not actor:
        raise HTTPException(status_code=400, detail="Actor requis")
    if role not in {"admin", "adv"}:
        raise HTTPException(status_code=400, detail="Rôle invalide (admin|adv)")

    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute(
            """
            INSERT INTO user_roles (actor, role, is_active, updated_by, created_at, updated_at)
            VALUES (?, ?, 1, ?, datetime('now'), datetime('now'))
            ON CONFLICT(actor) DO UPDATE SET
              role=excluded.role,
              is_active=1,
              updated_by=excluded.updated_by,
              updated_at=datetime('now')
            """,
            [actor, role, admin_actor],
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Mise à jour du rôle impossible: {exc}")

    save_audit_event("__roles__", "role_upsert", admin_actor, {"actor": actor, "role": role}, "ok")
    return {
        "ok": True,
        "actor": actor,
        "role": role,
        "effective_role": _resolve_role(actor),
    }


@app.delete("/api/admin/roles/{actor:path}")
def api_admin_delete_role(actor: str, req: Request):
    """Deactivate one DB role assignment (fallback to env/default mapping)."""
    admin_actor, _ = _ensure_admin(req)
    _init_db()

    target = _normalize_actor_identity(actor)
    if not target:
        raise HTTPException(status_code=400, detail="Actor requis")

    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        cur = conn.execute(
            """
            UPDATE user_roles
            SET is_active=0, updated_by=?, updated_at=datetime('now')
            WHERE actor=?
            """,
            [admin_actor, target],
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Suppression du rôle impossible: {exc}")

    save_audit_event("__roles__", "role_delete", admin_actor, {"actor": target}, "ok")
    return {
        "ok": True,
        "actor": target,
        "removed": cur.rowcount > 0,
        "effective_role": _resolve_role(target),
    }

@app.post("/api/settings/sftp-test")
def api_sftp_test():
    ok, msg = _test_sftp()
    return {"ok": ok, "message": msg}


# ── Download ───────────────────────────────────────────────────────────────────
@app.get("/api/download/{filename:path}")
def api_download(filename: str):
    safe = Path(filename).name  # prevent path traversal
    for d in (OUTBOX_DIR, tempfile.gettempdir()):
        fp = Path(d) / safe
        if fp.exists():
            return FileResponse(str(fp), filename=safe,
                                media_type="application/octet-stream")
    raise HTTPException(404, f"Fichier {safe} introuvable")


# ── File2EDI React SPA API (bridges frontend ↔ engine ↔ Databricks) ───────────
try:
    from src.file2edi import create_router as _f2e_create_router
    app.include_router(_f2e_create_router(), prefix="/api")
    log.info("File2EDI React API router mounted at /api/*")
except Exception as _f2e_exc:
    log.warning("File2EDI router not mounted: %s", _f2e_exc)

# ── SPA static assets (React only) ─────────────────────────────────────────────
_FRONTEND_DIST = APP_ROOT / "frontend" / "dist"
STATIC_DIR = _FRONTEND_DIST
INDEX_HTML = _FRONTEND_DIST / "index.html"
if INDEX_HTML.exists():
    log.info("UI: React SPA (frontend/dist)")
else:
    log.warning("frontend/dist missing — run: cd frontend && npm install && npm run build")

# ══════════════════════════════════════════════════════════════════════════════
# FULL PLATFORM BACKEND  (n8n → File2EDI migration)
# Migration map:
#   n8n WaitUserDecision      → REVIEW_REQUIRED status + validation cockpit UI
#   n8n Email* nodes          → /api/notifications/preview-rejection + send
#   n8n LedgerOrderSeen/Write → conversions + dedupe_ledger + audit_events
#   n8n DataTables            → bundled CSV files + /api/masterdata/*/search
#   n8n ApiBuildEdifact       → _local_process_and_respond (local engine)
#   n8n SftpUploadTstToEsker  → /api/conversions/{id}/send-sftp
# ══════════════════════════════════════════════════════════════════════════════

import json as _json
import csv as _csv

CONV_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversions (
  id                     TEXT PRIMARY KEY,
  correlation_id         TEXT,
    callback_url           TEXT,
  source_filename        TEXT NOT NULL,
  pdf_hash               TEXT,
  status                 TEXT NOT NULL DEFAULT 'PROCESSING',
  business_status        TEXT,
  delivery_status        TEXT DEFAULT 'NOT_APPLICABLE',
  po_number              TEXT,
  order_date             TEXT,
  delivery_date          TEXT,
  soldto                 TEXT,
  shipto                 TEXT,
  customer_name          TEXT,
  confidence             INTEGER DEFAULT 0,
  line_count             INTEGER DEFAULT 0,
  missing_material_count INTEGER DEFAULT 0,
  rejection_code         TEXT,
  rejection_message      TEXT,
  tst_filename           TEXT,
  edifact_content        TEXT,
  sftp_status            TEXT DEFAULT 'NOT_APPLICABLE',
  email_status           TEXT DEFAULT 'NOT_APPLICABLE',
  operator               TEXT DEFAULT 'system',
  corrections_json       TEXT,
  extraction_json        TEXT,
  created_at             TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at             TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_conv_status     ON conversions(status);
CREATE INDEX IF NOT EXISTS idx_conv_soldto     ON conversions(soldto);
CREATE INDEX IF NOT EXISTS idx_conv_po         ON conversions(po_number);
CREATE INDEX IF NOT EXISTS idx_conv_created    ON conversions(created_at);

CREATE TABLE IF NOT EXISTS audit_events (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  conversion_id TEXT NOT NULL,
  event_type    TEXT NOT NULL,
  actor         TEXT DEFAULT 'system',
  payload       TEXT,
  result        TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_conv_id   ON audit_events(conversion_id);
CREATE INDEX IF NOT EXISTS idx_audit_event     ON audit_events(event_type);

CREATE TABLE IF NOT EXISTS user_roles (
    actor      TEXT PRIMARY KEY,
    role       TEXT NOT NULL CHECK (role IN ('admin','adv')),
    is_active  INTEGER NOT NULL DEFAULT 1,
    updated_by TEXT DEFAULT 'system',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_user_roles_role   ON user_roles(role);
CREATE INDEX IF NOT EXISTS idx_user_roles_active ON user_roles(is_active);
"""

def _init_db() -> None:
    """Create all tables in the SQLite DB if they do not exist."""
    try:
        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.executescript(CONV_SCHEMA)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(conversions)").fetchall()}
        if "callback_url" not in cols:
            conn.execute("ALTER TABLE conversions ADD COLUMN callback_url TEXT")
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("_init_db failed: %s", e)


def _add_audit(conversion_id: str, event_type: str,
               actor: str = "system", payload: dict | None = None,
               result: str | None = None) -> None:
    """Append one audit event row."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute(
            "INSERT INTO audit_events (conversion_id,event_type,actor,payload,result,created_at)"
            " VALUES (?,?,?,?,?,datetime('now'))",
            [conversion_id, event_type, actor,
             _json.dumps(payload or {}), result or ""],
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("_add_audit(%s,%s): %s", conversion_id, event_type, e)


def _sanitize_callback_url(raw: str | None) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return None


def _load_conversion_callback_context(conversion_id: str) -> dict | None:
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id,correlation_id,callback_url,source_filename,pdf_hash,status,business_status,"
            "delivery_status,po_number,soldto,shipto,tst_filename,sftp_status,email_status,"
            "rejection_code,rejection_message,created_at,updated_at "
            "FROM conversions WHERE id=?",
            [conversion_id],
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as exc:
        log.warning("_load_conversion_callback_context(%s): %s", conversion_id, exc)
        return None


def _emit_conversion_callback(conversion_id: str, event_type: str, actor: str = "system",
                              payload: dict | None = None) -> None:
    context = _load_conversion_callback_context(conversion_id)
    if not context:
        return
    callback_url = _sanitize_callback_url(context.get("callback_url"))
    if not callback_url:
        return
    body = {
        "event_type": event_type,
        "actor": actor,
        "conversion": context,
        "payload": payload or {},
        "emitted_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        import requests as _req
        resp = _req.post(callback_url, json=body, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("conversion callback failed for %s -> %s: %s", conversion_id, callback_url, exc)
        _add_audit(conversion_id, "callback_failed", actor, {
            "callback_url": callback_url,
            "event_type": event_type,
            "error": str(exc),
        }, "CALLBACK_FAILED")
    else:
        _add_audit(conversion_id, "callback_sent", actor, {
            "callback_url": callback_url,
            "event_type": event_type,
            "http_status": resp.status_code,
        }, "CALLBACK_SENT")



# ══════════════════════════════════════════════════════════════════════════════
# PERSISTENCE ADAPTER  — Three-tier: Delta ▶ Workspace-JSONL ▶ SQLite
# ─────────────────────────────────────────────────────────────────────────────
#
# TIER 1 — Delta tables (preferred, scalable, persistent)
#   Requires one-time admin setup:
#     GRANT CREATE, USAGE ON SCHEMA <cat>.<schema>
#       TO `afa4186f-eea1-4f6e-9fe4-cd9eb0d3910a`;
#   Then set in app.yaml:
#     DATABRICKS_WAREHOUSE_ID: "607eec0346978542"
#     EDIFACT_CATALOG: "bci_rbs_prod"   # or any UC-managed catalog
#     EDIFACT_SCHEMA:  "edifact_generator"
#
# TIER 2 — Workspace JSONL (no admin needed, user-grantable)
#   User grants app SP CAN_EDIT on the EDIFACT workspace folder once:
#     Workspace UI → /Users/rsr1dy@bosch.com/EDIFACT → Permissions
#     → Add  afa4186f-eea1-4f6e-9fe4-cd9eb0d3910a  as CAN_EDIT
#   Or set DATABRICKS_PERSIST_TOKEN with a PAT that has write access.
#   Optional: DATABRICKS_PERSIST_PATH (defaults to EDIFACT/data/persist/)
#
# TIER 3 — Container SQLite (fallback, NOT persistent across redeploys)
#   Current default until admin/user sets up Tier 1 or 2.
# ══════════════════════════════════════════════════════════════════════════════

import threading as _threading
import base64    as _b64
import time      as _time

_PERSIST_LOCK    = _threading.Lock()
_PERSIST_BACKEND: dict = {}          # populated by _detect_and_init_backend()
_WS_CACHE:        dict = {}          # {path: (content, ts)} for workspace JSONL reads
_WS_CACHE_TTL = 10.0                 # seconds; short TTL to keep data fresh


# ─────────────────────────────────────────────────────────────────────────────
# Backend detection (called once during startup init)
# ─────────────────────────────────────────────────────────────────────────────

def _detect_and_init_backend() -> None:
    """Probe backends in priority order and cache the result in _PERSIST_BACKEND."""
    global _PERSIST_BACKEND

    warehouse_id  = os.environ.get("DATABRICKS_WAREHOUSE_ID", "").strip()
    cat           = os.environ.get("EDIFACT_CATALOG", "hive_metastore").strip()
    schema        = os.environ.get("EDIFACT_SCHEMA",  "edifact_generator").strip()
    # Default persist path: APP_ROOT/data/persist  (workspace FUSE path accessible via API)
    _app_root_str = str(APP_ROOT)
    _ws_base      = _app_root_str.replace("/Workspace", "").lstrip("/")  # strip /Workspace prefix
    persist_path  = os.environ.get(
        "DATABRICKS_PERSIST_PATH",
        f"/Users/{_ws_base}/data/persist" if "/Users/" in _app_root_str else None,
    )

    # ── Tier 1: Delta ──────────────────────────────────────────────────────
    if warehouse_id and cat and cat not in ("hive_metastore", ""):
        try:
            from databricks.sdk import WorkspaceClient
            from databricks.sdk.service.sql import StatementState, Format, Disposition
            w   = WorkspaceClient()
            t_conv  = f"`{cat}`.`{schema}`.file2edi_conversions"
            t_audit = f"`{cat}`.`{schema}`.file2edi_audit_events"

            def _delta_exec(sql: str) -> tuple[bool, list]:
                r = w.statement_execution.execute_statement(
                    warehouse_id=warehouse_id, statement=sql,
                    wait_timeout="30s", format=Format.JSON_ARRAY, disposition=Disposition.INLINE,
                )
                ok   = r.status.state == StatementState.SUCCEEDED
                rows = r.result.data_array if (ok and r.result) else []
                return ok, rows

            # Create schema + tables (idempotent)
            _delta_exec(f"CREATE SCHEMA IF NOT EXISTS `{cat}`.`{schema}`")
            conv_ddl = f"""
            CREATE TABLE IF NOT EXISTS {t_conv} (
              id STRING NOT NULL, correlation_id STRING, source_filename STRING,
              pdf_hash STRING, order_key STRING, status STRING DEFAULT 'PROCESSING',
              business_status STRING, delivery_status STRING DEFAULT 'NOT_APPLICABLE',
              po_number STRING, order_date STRING, delivery_date STRING,
              soldto STRING, shipto STRING, customer_name STRING,
              confidence INT DEFAULT 0, line_count INT DEFAULT 0,
              missing_material_count INT DEFAULT 0,
              rejection_code STRING, rejection_message STRING,
              tst_filename STRING, edifact_content STRING,
              sftp_status STRING DEFAULT 'NOT_APPLICABLE',
              email_status STRING DEFAULT 'NOT_APPLICABLE',
              operator STRING DEFAULT 'system',
              corrections_json STRING, extraction_json STRING,
              created_at STRING, updated_at STRING
            ) USING DELTA TBLPROPERTIES ('delta.autoOptimize.optimizeWrite'='true')
            """
            audit_ddl = f"""
            CREATE TABLE IF NOT EXISTS {t_audit} (
              id INTEGER, conversion_id STRING NOT NULL, event_type STRING NOT NULL,
              actor STRING DEFAULT 'system', payload STRING, result STRING,
              created_at STRING
            ) USING DELTA
            """
            ok1, _ = _delta_exec(conv_ddl)
            ok2, _ = _delta_exec(audit_ddl)
            if ok1 and ok2:
                _PERSIST_BACKEND = {
                    "backend": "delta", "persistent": True,
                    "location": f"{cat}.{schema}", "warehouse_id": warehouse_id,
                    "t_conv": t_conv, "t_audit": t_audit,
                    "_delta_exec": _delta_exec,
                    "conversions_available": True, "audit_events_available": True,
                    "note": f"Delta tables at {cat}.{schema} via warehouse {warehouse_id}",
                }
                log.info("persistence: delta backend active at %s.%s", cat, schema)
                return
            else:
                log.warning("persistence: delta DDL failed; trying next tier")
        except Exception as exc:
            log.warning("persistence: delta probe failed: %s", exc)

    # ── Tier 2: Workspace JSONL ────────────────────────────────────────────
    if persist_path:
        try:
            _ws_probe(persist_path)   # raises if not writable
            _PERSIST_BACKEND = {
                "backend": "workspace_jsonl", "persistent": True,
                "location": persist_path,
                "path_conv":  f"{persist_path}/conversions.jsonl",
                "path_audit": f"{persist_path}/audit_events.jsonl",
                "conversions_available": True, "audit_events_available": True,
                "note": f"Workspace JSONL files at {persist_path}",
            }
            log.info("persistence: workspace_jsonl backend active at %s", persist_path)
            return
        except Exception as exc:
            log.warning("persistence: workspace_jsonl probe failed: %s", exc)

    # ── Tier 3: SQLite fallback ────────────────────────────────────────────
    _PERSIST_BACKEND = {
        "backend": "sqlite", "persistent": False,
        "location": str(DB_PATH),
        "conversions_available": True, "audit_events_available": True,
        "note": (
            "Container SQLite — data is lost on redeploy. "
            "Set DATABRICKS_WAREHOUSE_ID + grant CREATE/USAGE on schema to enable Delta, "
            "or grant app SP CAN_EDIT on EDIFACT workspace folder to enable Workspace JSONL."
        ),
    }
    log.info("persistence: sqlite fallback active at %s", DB_PATH)


# ─────────────────────────────────────────────────────────────────────────────
# Workspace JSONL helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ws_headers() -> dict:
    """Return auth headers for workspace REST API calls."""
    token = os.environ.get("DATABRICKS_PERSIST_TOKEN") or os.environ.get("DATABRICKS_TOKEN", "")
    if token:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # OAuth via SDK (App SP auto-token)
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        token = w.config.token or ""
        if token:
            return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    except Exception:
        pass
    return {"Content-Type": "application/json"}

def _ws_api(method: str, endpoint: str, **kwargs) -> "requests.Response":
    import requests as _req
    url = f"https://{DATABRICKS_HOST}{endpoint}"
    resp = _req.request(method, url, headers=_ws_headers(), timeout=30, **kwargs)
    return resp

def _ws_probe(base_path: str) -> None:
    """Test write+read access to the persist folder.  No workspace/delete ever called.

    Uses conversions.jsonl.tmp as the probe target so the write is harmless if left
    behind — the first real JSONL write will overwrite it (Req 3+4+5).
    """
    probe_path = f"{base_path}/conversions.jsonl.tmp"
    probe_content = _b64.b64encode(b"[]\n").decode()   # valid empty JSONL, safe if left
    r = _ws_api("POST", "/api/2.0/workspace/import", json={
        "path": probe_path, "format": "AUTO",
        "content": probe_content, "overwrite": True,
    })
    if r.status_code not in (200, 201):
        raise RuntimeError(f"workspace write probe HTTP {r.status_code}: {r.text[:120]}")
    r2 = _ws_api("GET", "/api/2.0/workspace/get-status", params={"path": probe_path})
    if r2.status_code != 200:
        raise RuntimeError(f"workspace read probe HTTP {r2.status_code}")
    # No delete — .tmp file left in place; overwritten on first real JSONL write

def _ws_read_jsonl(ws_path: str) -> list[dict]:
    """Read JSONL from workspace, with short-lived cache. Returns [] if absent."""
    now = _time.monotonic()
    cached = _WS_CACHE.get(ws_path)
    if cached and (now - cached[1]) < _WS_CACHE_TTL:
        return cached[0]
    r = _ws_api("GET", "/api/2.0/workspace/export",
                params={"path": ws_path, "format": "AUTO", "direct_download": "true"})
    if r.status_code == 404:
        return []
    r.raise_for_status()
    text = r.text or ""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            try: rows.append(_json.loads(line))
            except Exception: pass
    _WS_CACHE[ws_path] = (rows, now)
    return rows

def _ws_write_jsonl(ws_path: str, rows: list[dict]) -> None:
    """Atomic JSONL write: stage → verify → promote.  No workspace/delete ever called.

    The staging file (ws_path + ".tmp") is intentionally left in place after each
    write cycle — it is overwritten by the next write (Req 3+4+5).  If stage-verify
    or promote fails, ws_path is untouched and the caller's except block fires (Req 6).
    """
    text    = "\n".join(_json.dumps(r, default=str) for r in rows) + "\n"
    encoded = _b64.b64encode(text.encode("utf-8")).decode("ascii")
    base_payload = {"format": "AUTO", "content": encoded, "overwrite": True}
    tmp_path = ws_path + ".tmp"

    # Stage: write to temp path first
    r1 = _ws_api("POST", "/api/2.0/workspace/import", json={**base_payload, "path": tmp_path})
    r1.raise_for_status()

    # Verify: lightweight existence check (get-status, no content download)
    r2 = _ws_api("GET", "/api/2.0/workspace/get-status", params={"path": tmp_path})
    if r2.status_code != 200:
        raise RuntimeError(
            f"_ws_write_jsonl: stage-verify failed for {tmp_path} (HTTP {r2.status_code})"
        )

    # Promote: overwrite final path (idempotent on retry; .tmp intentionally kept)
    r3 = _ws_api("POST", "/api/2.0/workspace/import", json={**base_payload, "path": ws_path})
    r3.raise_for_status()

    _WS_CACHE.pop(ws_path, None)  # invalidate read cache


# ─────────────────────────────────────────────────────────────────────────────
# Delta SQL helpers
# ─────────────────────────────────────────────────────────────────────────────

def _delta_exec(sql: str) -> tuple[bool, list[dict]]:
    """Execute SQL on the configured warehouse; return (ok, rows)."""
    fn = _PERSIST_BACKEND.get("_delta_exec")
    if not fn:
        return False, []
    ok, raw_rows = fn(sql)
    return ok, raw_rows   # raw_rows already list[list]

def _delta_rows_to_dicts(sql: str, cols: list[str]) -> list[dict]:
    """Execute SELECT, map col names onto rows."""
    ok, rows = _delta_exec(sql)
    if not ok or not rows:
        return []
    return [dict(zip(cols, r)) for r in rows]

_CONV_COLS = [
    "id","correlation_id","source_filename","pdf_hash","order_key","status",
    "business_status","delivery_status","po_number","order_date","delivery_date",
    "soldto","shipto","customer_name","confidence","line_count",
    "missing_material_count","rejection_code","rejection_message",
    "tst_filename","edifact_content","sftp_status","email_status","operator",
    "corrections_json","extraction_json","created_at","updated_at",
]
_AUDIT_COLS = ["id","conversion_id","event_type","actor","payload","result","created_at"]

def _q(v) -> str:
    """Escape a value for inline SQL (Delta MERGE). Never used for user input."""
    if v is None: return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC ADAPTER — the six canonical functions
# ─────────────────────────────────────────────────────────────────────────────

def get_storage_mode() -> dict:
    """Return storage backend descriptor for diagnostics and /api/proxy/health.

    For workspace_jsonl: adds live `file_exists` via a lightweight get-status call.
    For sqlite: adds `db_exists` and `db_size_kb` from the local filesystem.
    All fields required by Req 2: backend, persistent, location, file_exists/db_exists, note.
    """
    b = _PERSIST_BACKEND.copy()
    b.pop("_delta_exec", None)   # not JSON-serialisable
    if not b:
        db_here = Path(DB_PATH).exists()
        return {
            "backend": "sqlite", "persistent": False,
            "location": str(DB_PATH),
            "db_exists": db_here,
            "db_size_kb": round(Path(DB_PATH).stat().st_size / 1024, 1) if db_here else 0,
            "conversions_available": True, "audit_events_available": True,
            "note": "Backend not yet initialised (startup pending).",
        }
    bk = b.get("backend", "sqlite")
    if bk == "sqlite":
        db_here = Path(DB_PATH).exists()
        b["db_exists"]   = db_here
        b["db_size_kb"]  = round(Path(DB_PATH).stat().st_size / 1024, 1) if db_here else 0
    elif bk == "workspace_jsonl":
        conv_path = b.get("path_conv", "")
        try:
            r = _ws_api("GET", "/api/2.0/workspace/get-status", params={"path": conv_path})
            b["file_exists"] = r.status_code == 200
        except Exception:
            b["file_exists"] = False
    return b


# ─────────────────────────────────────────────────────────────────────────────
# SQLite write helpers (fallback path for workspace_jsonl failures)
# ─────────────────────────────────────────────────────────────────────────────

def _sqlite_save_conversion(row: dict) -> None:
    """Upsert one conversion into container-local SQLite (Req 6 fallback)."""
    conn = sqlite3.connect(DB_PATH, timeout=5)
    try:
        sets     = ", ".join(f"{c}=excluded.{c}" for c in _CONV_COLS if c not in ("id", "created_at"))
        cols_str = ", ".join(_CONV_COLS)
        qmarks   = ", ".join("?" for _ in _CONV_COLS)
        conn.execute(
            f"INSERT INTO conversions ({cols_str}) VALUES ({qmarks})"
            f" ON CONFLICT(id) DO UPDATE SET {sets}, updated_at=datetime('now')",
            [row.get(c) for c in _CONV_COLS],
        )
        conn.commit()
    except Exception as exc:
        log.warning("_sqlite_save_conversion(%s): %s", row.get("id"), exc)
    finally:
        conn.close()


def _sqlite_append_audit(
    conversion_id: str,
    event_type:    str,
    actor:         str         = "system",
    payload:       dict | None = None,
    result:        str | None  = None,
) -> None:
    """Append one audit event to container-local SQLite (Req 6 fallback)."""
    _add_audit(conversion_id, event_type, actor, payload, result)


def save_conversion(row: dict) -> None:
    """Upsert a single conversion. Routes to active backend."""
    bk = _PERSIST_BACKEND.get("backend", "sqlite")

    if bk == "delta":
        t = _PERSIST_BACKEND["t_conv"]
        sets = ", ".join(
            f"tgt.{c}=src.{c}" for c in _CONV_COLS if c not in ("id", "created_at")
        )
        vals = ", ".join(_q(row.get(c)) for c in _CONV_COLS)
        sql = f"""
        MERGE INTO {t} AS tgt
        USING (SELECT {', '.join(f'{_q(row.get(c))} AS {c}' for c in _CONV_COLS)}) AS src
        ON tgt.id = src.id
        WHEN MATCHED THEN UPDATE SET {sets}
        WHEN NOT MATCHED THEN INSERT ({', '.join(_CONV_COLS)}) VALUES ({vals})
        """
        ok, _ = _delta_exec(sql)
        if not ok:
            log.warning("save_conversion(%s): delta merge failed", row.get("id"))

    elif bk == "workspace_jsonl":
        try:
            with _PERSIST_LOCK:
                ws_path  = _PERSIST_BACKEND["path_conv"]
                existing = _ws_read_jsonl(ws_path)
                existing = [r for r in existing if r.get("id") != row.get("id")]
                existing.append(row)
                _ws_write_jsonl(ws_path, existing)
        except Exception as _wje:
            log.warning(
                "save_conversion(%s): workspace_jsonl write failed (%s) — SQLite fallback",
                row.get("id"), _wje,
            )
            _sqlite_save_conversion(row)

    else:  # sqlite fallback
        conn = sqlite3.connect(DB_PATH, timeout=5)
        try:
            sets = ", ".join(f"{c}=excluded.{c}" for c in _CONV_COLS if c not in ("id","created_at"))
            cols_str = ", ".join(_CONV_COLS)
            qmarks   = ", ".join("?" for _ in _CONV_COLS)
            conn.execute(f"""
            INSERT INTO conversions ({cols_str})
            VALUES ({qmarks})
            ON CONFLICT(id) DO UPDATE SET {sets}, updated_at=datetime('now')
            """, [row.get(c) for c in _CONV_COLS])
            conn.commit()
        except Exception as exc:
            log.warning("save_conversion(%s) sqlite: %s", row.get("id"), exc)
        finally:
            conn.close()


def load_conversion(cid: str) -> dict | None:
    """Load a single conversion by id. Returns None if not found."""
    bk = _PERSIST_BACKEND.get("backend", "sqlite")

    if bk == "delta":
        t = _PERSIST_BACKEND["t_conv"]
        rows = _delta_rows_to_dicts(
            f"SELECT {', '.join(_CONV_COLS)} FROM {t} WHERE id = {_q(cid)} LIMIT 1",
            _CONV_COLS
        )
        return rows[0] if rows else None

    if bk == "workspace_jsonl":
        ws_path = _PERSIST_BACKEND["path_conv"]
        rows = _ws_read_jsonl(ws_path)
        return next((r for r in rows if r.get("id") == cid), None)

    # sqlite
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM conversions WHERE id=?", [cid]).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as exc:
        log.warning("load_conversion(%s): %s", cid, exc)
        return None


def list_conversions(
    status:  str | None = None,
    limit:   int        = 200,
    q:       str | None = None,
) -> list[dict]:
    """List conversions newest-first, optional status/text filter."""
    bk = _PERSIST_BACKEND.get("backend", "sqlite")

    if bk == "delta":
        t = _PERSIST_BACKEND["t_conv"]
        where_parts = []
        if status: where_parts.append(f"status = {_q(status)}")
        if q:
            like = _q(f"%{q}%")
            where_parts.append(
                f"(po_number LIKE {like} OR source_filename LIKE {like} "
                f"OR customer_name LIKE {like} OR soldto LIKE {like})"
            )
        where = "WHERE " + " AND ".join(where_parts) if where_parts else ""
        return _delta_rows_to_dicts(
            f"SELECT {', '.join(_CONV_COLS)} FROM {t} {where} ORDER BY created_at DESC LIMIT {limit}",
            _CONV_COLS
        )

    if bk == "workspace_jsonl":
        ws_path = _PERSIST_BACKEND["path_conv"]
        rows = _ws_read_jsonl(ws_path)
        if status: rows = [r for r in rows if r.get("status") == status]
        if q:
            ql = q.lower()
            rows = [r for r in rows if any(
                ql in str(r.get(f, "")).lower()
                for f in ("po_number", "source_filename", "customer_name", "soldto")
            )]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[:limit]

    # sqlite
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.row_factory = sqlite3.Row
        clauses, params = [], []
        if status: clauses.append("status=?"); params.append(status)
        if q:
            like = f"%{q}%"
            clauses.append("(po_number LIKE ? OR source_filename LIKE ? OR customer_name LIKE ? OR soldto LIKE ?)")
            params.extend([like, like, like, like])
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM conversions {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit]
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("list_conversions: %s", exc)
        return []


def save_audit_event(
    conversion_id: str,
    event_type:    str,
    actor:         str         = "system",
    payload:       dict | None = None,
    result:        str | None  = None,
) -> None:
    """Append an audit event. Routes to active backend."""
    bk = _PERSIST_BACKEND.get("backend", "sqlite")

    if bk == "delta":
        t = _PERSIST_BACKEND["t_audit"]
        p_json = _q(_json.dumps(payload or {}))
        ok, _ = _delta_exec(f"""
        INSERT INTO {t} (conversion_id, event_type, actor, payload, result, created_at)
        VALUES ({_q(conversion_id)}, {_q(event_type)}, {_q(actor)},
                {p_json}, {_q(result or "")}, {_q(_datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'))})
        """)
        if not ok:
            log.warning("save_audit_event(%s,%s): delta insert failed", conversion_id, event_type)
        return

    if bk == "workspace_jsonl":
        import uuid as _uuid
        event = {
            "id": str(_uuid.uuid4()),
            "conversion_id": conversion_id,
            "event_type": event_type,
            "actor": actor,
            "payload": _json.dumps(payload or {}),
            "result": result or "",
            "created_at": _datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        try:
            with _PERSIST_LOCK:
                ws_path = _PERSIST_BACKEND["path_audit"]
                rows    = _ws_read_jsonl(ws_path)
                rows.append(event)
                _ws_write_jsonl(ws_path, rows)
        except Exception as _wje:
            log.warning(
                "save_audit_event(%s,%s): workspace_jsonl write failed (%s) — SQLite fallback",
                conversion_id, event_type, _wje,
            )
            _sqlite_append_audit(conversion_id, event_type, actor, payload, result)
        return

    # sqlite — delegate to existing _add_audit
    _add_audit(conversion_id, event_type, actor, payload, result)


def list_audit_events(conversion_id: str) -> list[dict]:
    """List audit events for a conversion, oldest first."""
    bk = _PERSIST_BACKEND.get("backend", "sqlite")

    if bk == "delta":
        t = _PERSIST_BACKEND["t_audit"]
        return _delta_rows_to_dicts(
            f"SELECT {', '.join(_AUDIT_COLS)} FROM {t} "
            f"WHERE conversion_id = {_q(conversion_id)} ORDER BY created_at ASC",
            _AUDIT_COLS
        )

    if bk == "workspace_jsonl":
        ws_path = _PERSIST_BACKEND["path_audit"]
        rows = _ws_read_jsonl(ws_path)
        return sorted(
            [r for r in rows if r.get("conversion_id") == conversion_id],
            key=lambda r: r.get("created_at", ""),
        )

    # sqlite
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM audit_events WHERE conversion_id=? ORDER BY created_at ASC",
            [conversion_id]
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("list_audit_events(%s): %s", conversion_id, exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Migration helper  (SQLite → new backend, run once on first startup after
# migration — writes a storage_migration_checked audit event when done)
# ─────────────────────────────────────────────────────────────────────────────

def _maybe_migrate_sqlite_to_backend() -> None:
    """If backend != sqlite AND local DB has data, migrate it once.

    Uses a `migration_sentinel.json` file in the persist folder as the primary
    idempotency guard for workspace_jsonl (Req 3+9).  Falls back to scanning
    audit_events for a `storage_migration_checked` event (Delta + defensive path).
    """
    bk = _PERSIST_BACKEND.get("backend", "sqlite")
    if bk == "sqlite":
        return  # nothing to do
    if not Path(DB_PATH).exists():
        return  # no local data

    # ── Idempotency check ────────────────────────────────────────────────────
    sentinel_key  = "storage_migration_checked"

    if bk == "workspace_jsonl":
        # Primary guard: migration_sentinel.json file (lightweight get-status check)
        base_path = _PERSIST_BACKEND.get("path_conv", "").rsplit("/", 1)[0]
        sentinel_ws_path = base_path + "/migration_sentinel.json"
        try:
            r_chk = _ws_api("GET", "/api/2.0/workspace/get-status",
                            params={"path": sentinel_ws_path})
            if r_chk.status_code == 200:
                log.info("migration: sentinel file found — skipping (already migrated)")
                return
        except Exception:
            pass  # can't check → proceed with migration (write sentinel at end)
    else:
        # Delta / other: scan audit events for sentinel
        try:
            if any(e.get("event_type") == sentinel_key for e in list_audit_events("__migration__")):
                return
        except Exception:
            pass

    # ── Read SQLite source ───────────────────────────────────────────────────
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.row_factory = sqlite3.Row
        existing_convs = [dict(r) for r in
                          conn.execute("SELECT * FROM conversions ORDER BY created_at").fetchall()]
        existing_audit = [dict(r) for r in
                          conn.execute("SELECT * FROM audit_events ORDER BY created_at").fetchall()]
        conn.close()
    except Exception as exc:
        log.warning("migration: could not read SQLite source: %s", exc)
        return

    if not existing_convs and not existing_audit:
        log.info("migration: SQLite source is empty — nothing to migrate")
        if bk == "workspace_jsonl":
            _ws_write_migration_sentinel(sentinel_ws_path, 0, 0, bk)
        return

    # ── Migrate rows ─────────────────────────────────────────────────────────
    migrated_conv = migrated_audit = 0
    for row in existing_convs:
        try:
            save_conversion(row)
            migrated_conv += 1
        except Exception as exc:
            log.warning("migration: skip conv %s: %s", row.get("id"), exc)
    for evt in existing_audit:
        try:
            save_audit_event(
                evt.get("conversion_id", "?"),
                evt.get("event_type", "migrated"),
                evt.get("actor", "migration"),
                _json.loads(evt.get("payload") or "{}"),
                evt.get("result"),
            )
            migrated_audit += 1
        except Exception as exc:
            log.warning("migration: skip audit %s: %s", evt.get("id"), exc)

    # ── Write sentinel (idempotency guard for next startup) ──────────────────
    if bk == "workspace_jsonl":
        _ws_write_migration_sentinel(sentinel_ws_path, migrated_conv, migrated_audit, bk)
    else:
        # Delta: write sentinel as audit event
        save_audit_event(
            "__migration__", sentinel_key, "system",
            {"migrated_conversions": migrated_conv, "migrated_audit_events": migrated_audit,
             "source": str(DB_PATH), "target_backend": bk},
            "OK" if migrated_conv + migrated_audit > 0 else "EMPTY_SOURCE",
        )
    log.info("migration: %d conversions + %d audit events → %s", migrated_conv, migrated_audit, bk)


def _ws_write_migration_sentinel(
    ws_path:        str,
    migrated_conv:  int,
    migrated_audit: int,
    bk:             str,
) -> None:
    """Write migration_sentinel.json to the persist folder (Req 3+9)."""
    sentinel_data = _json.dumps({
        "storage_migration_checked": True,
        "migrated_at":            _datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "migrated_conversions":   migrated_conv,
        "migrated_audit_events":  migrated_audit,
        "source":                 str(DB_PATH),
        "target_backend":         bk,
    }, default=str).encode("utf-8")
    try:
        r = _ws_api("POST", "/api/2.0/workspace/import", json={
            "path": ws_path, "format": "AUTO",
            "content": _b64.b64encode(sentinel_data).decode("ascii"),
            "overwrite": True,
        })
        if r.status_code not in (200, 201):
            log.warning("migration: sentinel write HTTP %d: %s", r.status_code, r.text[:80])
        else:
            log.info("migration: sentinel written to %s", ws_path)
    except Exception as exc:
        log.warning("migration: could not write sentinel file: %s", exc)

# ── end PERSISTENCE ADAPTER ───────────────────────────────────────────────────


def _upsert_conversion(data: dict, callback_url: str | None = None) -> None:
    """Insert or replace a conversion row from a proxy-convert result dict."""
    try:
        r   = data.get("rejection", {})
        cus = data.get("customer", {})
        ord = data.get("order", {})
        edi = data.get("edifact", {})
        lines = data.get("lines", {})
        dec   = r.get("decision") or "UNKNOWN"
        status_map = {
            "ACCEPTED": "ACCEPTED", "REJECTED": "REJECTED",
            "REVIEW": "REVIEW_REQUIRED",
        }
        status = status_map.get(dec, "FAILED" if data.get("status") == "ERROR" else "PROCESSING")
        missing = sum(1 for it in (lines.get("items") or [])
                      if (it.get("code_article","")).startswith("ARTICLE_MANQUANT"))
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute("""
          INSERT INTO conversions
                        (id, correlation_id, callback_url, source_filename, pdf_hash, status,
             po_number, order_date, delivery_date, soldto, shipto,
             customer_name, confidence, line_count, missing_material_count,
             rejection_code, rejection_message,
             tst_filename, edifact_content, extraction_json,
             created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))
          ON CONFLICT(id) DO UPDATE SET
                        callback_url=COALESCE(excluded.callback_url, conversions.callback_url),
            status=excluded.status, po_number=excluded.po_number,
            soldto=excluded.soldto, shipto=excluded.shipto,
            rejection_code=excluded.rejection_code,
            rejection_message=excluded.rejection_message,
            tst_filename=excluded.tst_filename,
            edifact_content=excluded.edifact_content,
            updated_at=datetime('now')
        """, [
            data.get("pdf_hash") or str(uuid.uuid4()),
            data.get("correlation_id"),
            _sanitize_callback_url(callback_url),
            data.get("filename", ""),
            data.get("pdf_hash"),
            status,
            ord.get("po_number"),
            ord.get("order_date"),
            ord.get("delivery_date"),
            cus.get("soldto"),
            cus.get("shipto"),
            cus.get("name"),
            cus.get("confidence", 0),
            lines.get("count", 0),
            missing,
            r.get("reason"),
            r.get("reason") and (REJECT_LABELS.get(r["reason"]) or r["reason"]),
            (data.get("filename","").replace(".pdf",".tst") if edi.get("generated") else None),
            edi.get("message"),
            _json.dumps(data),
        ])
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("_upsert_conversion: %s", e)


REJECT_LABELS = {
    "PDF_PARSE_FAILURE": "Échec lecture PDF",
    "CONTRACT_BREAK_SOLDTO_MISSING": "SOLDTO introuvable",
    "SOLDTO_NOT_FOUND": "Client donneur d'ordre introuvable",
    "SOLDTO_AMBIGUOUS_MATCH": "Plusieurs clients possibles",
    "SHIPTO_WEAK_EVIDENCE_IN_SOLDTO_FAMILY": "Preuve adresse livraison insuffisante",
    "SHIPTO_NO_STRONG_MATCH": "Aucune adresse de livraison trouvée",
    "SHIPTO_AMBIGUOUS_MATCH": "Plusieurs adresses de livraison possibles",
    "NO_DELIVERY_ADDRESS": "Adresse de livraison absente",
    "DELIVERY_ADDRESS_INVALID": "Adresse de livraison invalide",
    "ARTICLE_NOT_FOUND": "Article introuvable dans les données maîtres",
    "NO_LINE_ITEMS": "Aucune ligne article détectée",
    "QUANTITY_MISSING": "Quantité manquante",
    "PRICE_MISSING": "Prix manquant",
    "ORDER_KEY_MISSING": "Numéro de commande manquant",
    "PO_NUMBER_DUPLICATE": "Commande en doublon",
    "NOT_AN_ORDER": "Document non reconnu comme commande",
    "CUSTOMER_NOT_DEFINED": "Client non défini",
    "MASTERDATA_MISSING": "Données maîtres indisponibles",
    "CONTRACT_KEYWORD": "Mot-clé contrat/devis détecté",
    "EDIFACT_VALIDATION_FAILED": "Validation EDIFACT échouée",
}


def _csv_search(csv_name: str, q: str, cols: list[str], limit: int = 50) -> list[dict]:
    """Full-text search across specified columns in a bundled masterdata CSV."""
    q_lo = q.strip().lower()
    results = []
    try:
        fpath = os.path.join(MASTER_DATA_RUNTIME, csv_name)
        with open(fpath, encoding="utf-8", newline="") as f:
            reader = _csv.DictReader(f, delimiter=";")
            for row in reader:
                haystack = " ".join(str(row.get(c,"")) for c in cols).lower()
                if not q_lo or q_lo in haystack:
                    results.append(dict(row))
                    if len(results) >= limit:
                        break
    except Exception as e:
        log.warning("_csv_search(%s): %s", csv_name, e)
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  MASTERDATA IN-MEMORY CACHE  (pandas DataFrames — loaded once at startup)
#  Priority 2 fix: replaces CSV-file-per-call with in-memory search
# ══════════════════════════════════════════════════════════════════════════════
import threading as _threading

# {name: {"df": DataFrame | None, "rows": int, "loaded_at": str, "error": str|None}}
MASTERDATA_CACHE: dict = {}
_MC_LOCK = _threading.Lock()

_MD_FILES = {
    "customers":   "10564_Customers.csv",
    "partners":    "10564_Partners.csv",
    "materials":   "10564_Materials.csv",
    "salesorders": "DB_Salesorder.csv",
}

_MD_SEARCH_COLS = {
    "customers":   ["SOLDTO","NAME","ORT01","PSTLZ","STRAS","LAND1","VAT_NR"],
    "partners":    ["SOLDTO","SHIPTO","NAME","ORT01","PSTLZ","STRAS","PARVW"],
    "materials":   ["MATNR","MAKTX"],
    "salesorders": ["BSTNK","VBELN","KUNNR","ERDAT","BSTDK","ERNAM"],
}

# Required columns for schema validation per file (Req 3+6)
_MD_REQUIRED_COLS: dict[str, list[str]] = {
    "customers":   ["SOLDTO","NAME","ORT01","PSTLZ","STRAS","LAND1","VAT_NR"],
    "partners":    ["SOLDTO","SHIPTO","LAND1","NAME","ORT01","PSTLZ","STRAS","PARVW"],
    "materials":   ["MATNR","MAKTX"],
    "salesorders": ["VBELN","ERDAT","ERNAM","BSTNK","BSTDK","KUNNR"],
}

# Source type per key — updated by _load_masterdata_cache (Req 5)
_MD_SOURCE: dict[str, str] = {}     # "bundled" | "workspace" | "fallback" | "error"
_MD_LAST_SYNC: dict[str, str] = {}  # key → ISO timestamp of last successful workspace sync


def _load_masterdata_cache() -> dict:
    """Load all masterdata CSVs into DataFrames with schema validation and source tracking.

    Source priority per Req 5:
      Tier A — workspace-synced (same path; _MD_LAST_SYNC records the sync timestamp)
      Tier B — bundled CSV present at MASTER_DATA_RUNTIME
      Tier C — previous in-memory entry kept when reload fails
      Tier D — error entry, never fake success
    """
    import datetime as _dt
    try:
        import pandas as _pd
    except ImportError:
        log.warning("pandas not available — masterdata cache disabled")
        return {"error": "pandas not available"}

    with _MC_LOCK:
        for key, fname in _MD_FILES.items():
            fpath      = Path(MASTER_DATA_RUNTIME) / fname
            src_type   = "workspace" if key in _MD_LAST_SYNC else "bundled"
            prev_entry = MASTERDATA_CACHE.get(key)          # Tier C candidate
            try:
                df = _pd.read_csv(
                    str(fpath), sep=";", dtype=str,
                    keep_default_na=False, on_bad_lines="skip",
                    encoding="utf-8", encoding_errors="replace",
                )
                df.columns = [c.strip() for c in df.columns]
                schema_info = _validate_md_schema(key, df)
                try:
                    fsize_kb = round(fpath.stat().st_size / 1024, 1)
                except Exception:
                    fsize_kb = 0.0
                warnings: list[str] = []
                if not schema_info["schema_valid"]:
                    warnings.append(
                        f"Colonnes manquantes: {', '.join(schema_info['missing_columns'])}"
                    )
                if len(df) == 0:
                    warnings.append("Fichier vide")
                MASTERDATA_CACHE[key] = {
                    "df":               df,
                    "rows":             len(df),
                    "loaded_at":        _dt.datetime.now().isoformat(timespec="seconds"),
                    "error":            None,
                    "fname":            fname,
                    "source":           src_type,
                    "source_path":      str(fpath),
                    "file_size_kb":     fsize_kb,
                    "schema_valid":     schema_info["schema_valid"],
                    "required_columns": schema_info["required_columns"],
                    "present_columns":  schema_info["present_columns"],
                    "missing_columns":  schema_info["missing_columns"],
                    "warnings":         warnings,
                }
                _MD_SOURCE[key] = src_type
                log.info("MD cache: %s — %d rows  schema_valid=%s  source=%s",
                         fname, len(df), schema_info["schema_valid"], src_type)

            except FileNotFoundError:
                if prev_entry and prev_entry.get("df") is not None:
                    fallback = dict(prev_entry)
                    fallback["source"] = "fallback"
                    fallback["warnings"] = list(prev_entry.get("warnings", [])) + [
                        f"Fichier introuvable: {fpath} — données précédentes conservées."
                    ]
                    MASTERDATA_CACHE[key] = fallback
                    _MD_SOURCE[key] = "fallback"
                    log.warning("MD cache: %s MISSING — Tier C fallback active", fname)
                else:
                    MASTERDATA_CACHE[key] = {
                        "df": None, "rows": 0, "loaded_at": None,
                        "error": f"Fichier introuvable: {fpath}",
                        "fname": fname, "source": "error",
                        "schema_valid": False,
                        "required_columns": _MD_REQUIRED_COLS.get(key, []),
                        "present_columns": [], "missing_columns": [], "warnings": [],
                    }
                    _MD_SOURCE[key] = "error"
                    log.warning("MD cache load failed (%s): file not found", fname)

            except Exception as exc:
                if prev_entry and prev_entry.get("df") is not None:
                    fallback = dict(prev_entry)
                    fallback["source"] = "fallback"
                    fallback["warnings"] = list(prev_entry.get("warnings", [])) + [
                        f"Erreur rechargement: {exc} — données précédentes conservées."
                    ]
                    MASTERDATA_CACHE[key] = fallback
                    _MD_SOURCE[key] = "fallback"
                    log.warning("MD cache: %s ERROR — Tier C fallback: %s", fname, exc)
                else:
                    MASTERDATA_CACHE[key] = {
                        "df": None, "rows": 0, "loaded_at": None, "error": str(exc),
                        "fname": fname, "source": "error",
                        "schema_valid": False,
                        "required_columns": _MD_REQUIRED_COLS.get(key, []),
                        "present_columns": [], "missing_columns": [], "warnings": [],
                    }
                    _MD_SOURCE[key] = "error"
                    log.warning("MD cache load failed (%s): %s", fname, exc)

    return {k: {"rows": v["rows"], "loaded_at": v["loaded_at"], "error": v.get("error")}
            for k, v in MASTERDATA_CACHE.items()}


def _refresh_masterdata_cache() -> None:
    """Reload the cache (called after masterdata sync)."""
    _load_masterdata_cache()


# ─────────────────────────────────────────────────────────────────────────────
# Masterdata normalize helpers (Req 1)
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_masterdata_value(s: str) -> str:
    """Strip, upper-case, collapse whitespace."""
    return " ".join(str(s).strip().upper().split())


def _normalize_vat(vat: str) -> str:
    """Normalize VAT number: strip spaces, upper-case, keep alphanumeric."""
    return "".join(c for c in str(vat).upper() if c.isalnum())


def _normalize_postal(postal: str) -> str:
    """Normalize postal code: strip, keep alphanumeric only."""
    return "".join(c for c in str(postal).strip() if c.isalnum()).upper()


def _normalize_city(city: str) -> str:
    """Normalize city: strip, upper-case, Unicode-safe."""
    import unicodedata
    s = unicodedata.normalize("NFKD", str(city).strip().upper())
    return " ".join(s.split())


def _normalize_article_code(art: str) -> str:
    """Normalize article / MATNR code: strip, upper-case, strip leading zeros for numeric."""
    s = str(art).strip().upper()
    if s.isdigit():
        s = str(int(s))
    return s


def _validate_md_schema(key: str, df) -> dict:
    """Validate DataFrame columns against _MD_REQUIRED_COLS.  Returns validation dict."""
    required = _MD_REQUIRED_COLS.get(key, [])
    present  = list(df.columns) if df is not None else []
    missing  = [c for c in required if c not in present]
    return {
        "required_columns": required,
        "present_columns":  present,
        "missing_columns":  missing,
        "schema_valid":     len(missing) == 0,
    }


def _csv_search_cached(key: str, q: str, limit: int = 50) -> list[dict]:
    """Search in-memory cache for a masterdata table.  Falls back to file scan.

    Limit is clamped to 200 (Req 7).  Columns not present in the DataFrame are
    skipped so searches never raise KeyError on schema-mismatched files (Req 3).
    """
    limit     = min(int(limit or 50), 200)
    entry     = MASTERDATA_CACHE.get(key, {})
    df        = entry.get("df")
    cols      = _MD_SEARCH_COLS.get(key, [])
    if df is None:
        return _csv_search(_MD_FILES.get(key, ""), q, cols, limit)
    q_lo = q.strip().lower()
    if not q_lo:
        return df.head(limit).to_dict("records")
    # Only search columns that exist in this DataFrame (schema-safe)
    safe_cols = [c for c in cols if c in df.columns]
    if not safe_cols:
        return df.head(limit).to_dict("records")
    mask = df[safe_cols].apply(
        lambda c: c.str.lower().str.contains(q_lo, na=False)
    ).any(axis=1)
    return df[mask].head(limit).to_dict("records")


def _get_soldto_row(soldto_code: str) -> dict:
    """Look up a SOLDTO code in the customers cache. Returns builder-compatible dict."""
    entry = MASTERDATA_CACHE.get("customers", {})
    df = entry.get("df")
    if df is not None and soldto_code:
        rows = df[df["SOLDTO"].str.strip() == soldto_code.strip()]
        if not rows.empty:
            r = rows.iloc[0]
            return {
                "soldto": r.get("SOLDTO",""), "name": r.get("NAME",""),
                "street": r.get("STRAS",""), "city": r.get("ORT01",""),
                "postal_code": r.get("PSTLZ",""), "country": r.get("LAND1","FR"),
            }
    return {"soldto": soldto_code, "name": "", "street": "", "city": "",
            "postal_code": "", "country": "FR"}


def _get_shipto_row(shipto_code: str) -> dict:
    """Look up a SHIPTO code in the partners cache. Returns builder-compatible dict."""
    entry = MASTERDATA_CACHE.get("partners", {})
    df = entry.get("df")
    if df is not None and shipto_code:
        rows = df[df["SHIPTO"].str.strip() == shipto_code.strip()]
        if not rows.empty:
            r = rows.iloc[0]
            return {
                "shipto": r.get("SHIPTO",""), "soldto": r.get("SOLDTO",""),
                "name": r.get("NAME",""), "street": r.get("STRAS",""),
                "city": r.get("ORT01",""), "postal_code": r.get("PSTLZ",""),
                "country": r.get("LAND1","FR"),
            }
    return {"shipto": shipto_code, "soldto": "", "name": "", "street": "",
            "city": "", "postal_code": "", "country": "FR"}


def _run_edi_checklist(msg: str) -> list[dict]:
    """Run the 11-point EDIFACT validation checklist. Returns list of check results."""
    checks = [
        ("UNA",             msg.startswith("UNA"),                       True,  "UNA service string"),
        ("UNB+UNOC:3",      "UNB+UNOC:3" in msg,                        True,  "UNB syntaxe UNOC:3"),
        ("sender_gln",      "4399901876613" in msg,                      True,  "GLN expéditeur 4399901876613"),
        ("receiver_gln",    "3015981600108" in msg,                      True,  "GLN destinataire 3015981600108"),
        ("UNH",             "UNH+" in msg,                               True,  "UNH enveloppe message"),
        ("BGM",             "BGM+" in msg,                               True,  "BGM identification"),
        ("DTM_137",         "DTM+137:" in msg,                           True,  "DTM+137 date commande"),
        ("NAD_BY",          "NAD+BY+" in msg,                            True,  "NAD+BY donneur d'ordre"),
        ("NAD_DP",          "NAD+DP+" in msg,                            True,  "NAD+DP livraison"),
        ("LIN",             "LIN+" in msg,                               True,  "Au moins une ligne LIN"),
        ("UNZ",             "UNZ+" in msg,                               True,  "UNZ fermeture interchange"),
    ]
    lin_count = msg.count("LIN+")
    pia_count = msg.count("PIA+")
    qty_count = msg.count("QTY+")
    checks += [
        ("PIA_equals_LIN",  pia_count == lin_count and lin_count > 0,   False, f"PIA ({pia_count}) = LIN ({lin_count})"),
        ("QTY_equals_LIN",  qty_count == lin_count and lin_count > 0,   False, f"QTY ({qty_count}) = LIN ({lin_count})"),
    ]
    return [{"key": k, "ok": ok, "required": req, "label": lbl}
            for k, ok, req, lbl in checks]


# ══════════════════════════════════════════════════════════════════════════════
#  /api/conversions/{id}/generate
#  Priority 1: Re-run EDIFACT generation with operator corrections
# ══════════════════════════════════════════════════════════════════════════════

def _build_resolved_lines(cor: dict, orig_lines: dict) -> tuple[list[dict], list[str]]:
    """Build EDIFACT line dicts from review corrections (priority) or extraction fallback."""
    line_corrections = cor.get("lines") or []
    from_review = bool(cor.get("lines_from_review"))
    resolved_lines: list[dict] = []
    skipped_lines: list[str] = []

    def _append_from_correction(lc: dict) -> None:
        art = str(
            lc.get("matnr")
            or lc.get("code_article")
            or lc.get("boschArticle")
            or ""
        ).strip()
        if not art or art.upper().startswith("ARTICLE_MANQUANT"):
            skipped_lines.append(art or f"line_{lc.get('line_number', '?')}")
            return
        qty = lc.get("quantity")
        price = lc.get("unit_price")
        if price is None:
            price = lc.get("unitPrice")
        resolved_lines.append({
            "matnr": art,
            "description": str(lc.get("description") or lc.get("designation") or ""),
            "quantity": qty if qty is not None and qty != "" else "1",
            "unit_price": price if price is not None and price != "" else "",
            "unit": str(lc.get("unit") or "PCE").strip() or "PCE",
            "original_article": art,
        })

    if from_review or line_corrections:
        for lc in line_corrections:
            _append_from_correction(lc)
        return resolved_lines, skipped_lines

    items = orig_lines.get("items") or orig_lines.get("lignes") or []
    for i, it in enumerate(items):
        art = str(
            it.get("code_article")
            or it.get("Article Bosch")
            or it.get("matnr")
            or ""
        ).strip()
        if i < len(line_corrections):
            lc = line_corrections[i]
            art = str(lc.get("matnr") or lc.get("code_article") or art or "").strip()
        if not art or art.upper().startswith("ARTICLE_MANQUANT"):
            skipped_lines.append(art or f"line_{i}")
            continue
        qty = it.get("quantite", it.get("quantity", ""))
        price = it.get("prix_unitaire_ht", it.get("unit_price", ""))
        if i < len(line_corrections):
            lc = line_corrections[i]
            if lc.get("quantity") is not None:
                qty = lc.get("quantity")
            if lc.get("unit_price") is not None:
                price = lc.get("unit_price")
            elif lc.get("unitPrice") is not None:
                price = lc.get("unitPrice")
        resolved_lines.append({
            "matnr": art,
            "description": str(
                (line_corrections[i].get("description") if i < len(line_corrections) else None)
                or it.get("description")
                or it.get("Designation")
                or ""
            ),
            "quantity": qty,
            "unit_price": price,
            "unit": str(
                (line_corrections[i].get("unit") if i < len(line_corrections) else None)
                or it.get("unit")
                or it.get("Unite")
                or "PCE"
            ).strip() or "PCE",
            "original_article": art,
        })

    return resolved_lines, skipped_lines


def _merge_partner_override(base: dict, override: dict | None, id_key: str, code: str) -> dict:
    """Apply operator-edited partner fields over masterdata lookup (review wins)."""
    row = dict(base or {})
    if code:
        row[id_key] = code
    if not override:
        return row
    for src, dst in (
        ("name", "name"),
        ("street", "street"),
        ("postal_code", "postal_code"),
        ("city", "city"),
        ("country", "country"),
    ):
        val = override.get(src)
        if val is not None and str(val).strip():
            row[dst] = str(val).strip()
    return row


@app.post("/api/conversions/{cid}/generate")
async def api_generate(cid: str, req: Request):
    """Regenerate EDIFACT using stored extraction + operator corrections.

    Flow:
    1. Load conversion + corrections from SQLite.
    2. Merge corrections over original extraction.
    3. Look up SOLDTO/SHIPTO from masterdata cache.
    4. Call src.edifact_builder.build_orders_message directly.
    5. Run 11-point checklist.
    6. Write .tst to outbox.
    7. Update conversion status + edifact_content.
    8. Add audit event edifact_regenerated_from_review.
    """
    _init_db()
    try:
        request = await req.json()
    except Exception:
        request = {}
    actor, _ = _ensure_can_mutate(req, request)

    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        row = conn.execute(
            "SELECT extraction_json, corrections_json, source_filename, po_number, soldto, shipto"
            " FROM conversions WHERE id=?", [cid]
        ).fetchone()
        conn.close()
        if not row:
            return JSONResponse(status_code=404, content={"error": "Conversion introuvable"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    ext_raw, cor_raw, src_fname, db_po, db_soldto, db_shipto = row
    try:
        ext = _json.loads(ext_raw or "{}")
    except Exception:
        ext = {}
    try:
        cor = _json.loads(cor_raw or "{}")
    except Exception:
        cor = {}

    # Merge operator request body over stored corrections
    if request.get("corrections"):
        cor.update(request["corrections"])

    # ── Merge correction fields ──────────────────────────────────────────
    orig_order = ext.get("order", {})
    orig_cust  = ext.get("customer", {})
    orig_lines = ext.get("lines", {})

    po_number    = (cor.get("po_number")     or orig_order.get("po_number")     or db_po     or "").strip()
    order_date   = (cor.get("order_date")    or orig_order.get("order_date")    or "").strip()
    delivery_date= (cor.get("delivery_date") or orig_order.get("delivery_date") or "").strip()
    soldto_code  = (cor.get("soldto")        or orig_cust.get("soldto")         or db_soldto or "").strip()
    shipto_code  = (cor.get("shipto")        or orig_cust.get("shipto")         or db_shipto or "").strip()

    # ── Masterdata cache guardrail (Req 10) ─────────────────────────────
    _cust = MASTERDATA_CACHE.get("customers", {})
    _mats = MASTERDATA_CACHE.get("materials", {})
    md_blockers: list[dict] = []
    if _cust.get("rows", 0) == 0:
        md_blockers.append({
            "code": "MASTERDATA_MISSING",
            "message": "Cache clients vide — synchronisez les données maîtres avant de générer.",
        })
    elif _cust.get("schema_valid") is False:
        mc = _cust.get("missing_columns", [])
        md_blockers.append({
            "code": "MASTERDATA_SCHEMA_INVALID",
            "message": f"Schéma clients invalide — colonnes manquantes: {', '.join(mc)}",
        })
    if _mats.get("rows", 0) == 0:
        md_blockers.append({
            "code": "MASTERDATA_MISSING",
            "message": "Cache articles vide — les codes MATNR ne peuvent pas être validés.",
        })
    if md_blockers:
        save_audit_event(cid, "edifact_generation_failed", actor,
                         {"reason": "masterdata_missing", "blockers": md_blockers})
        return {
            "conversion_id": cid,
            "status":        "REVIEW_REQUIRED",
            "rejection_code": md_blockers[0]["code"],
            "blockers":      md_blockers,
            "message":       "Génération bloquée — données maîtres insuffisantes.",
        }

    # ── Validation: mandatory blockers ──────────────────────────────────
    blockers = []
    if not po_number:
        blockers.append({"code": "ORDER_KEY_MISSING", "message": "N° de commande manquant"})
    if not soldto_code:
        blockers.append({"code": "SOLDTO_NOT_FOUND", "message": "Code SOLDTO manquant"})
    if not shipto_code:
        blockers.append({"code": "SHIPTO_NO_STRONG_MATCH", "message": "Code SHIPTO manquant"})

    # ── Build resolved_lines ─────────────────────────────────────────────
    resolved_lines, skipped_lines = _build_resolved_lines(cor, orig_lines)

    if not resolved_lines:
        blockers.append({"code": "NO_LINE_ITEMS",
                         "message": f"Aucune ligne article valide ({len(skipped_lines)} ignorée(s))"})

    if blockers:
        blocker_messages = [
            b.get("message") or b.get("code") or str(b)
            for b in blockers
            if isinstance(b, dict)
        ]
        return {
            "conversion_id": cid,
            "status": "REVIEW_REQUIRED",
            "blockers": blockers,
            "errors": blocker_messages,
            "generated": False,
            "message": " — ".join(blocker_messages) if blocker_messages else (
                "Blocages restants — corrigez les champs avant de générer."
            ),
        }

    # ── Masterdata lookup ─────────────────────────────────────────────────
    soldto_row = _merge_partner_override(
        _get_soldto_row(soldto_code),
        cor.get("soldto_partner"),
        "soldto",
        soldto_code,
    )
    shipto_row = _merge_partner_override(
        _get_shipto_row(shipto_code),
        cor.get("shipto_partner"),
        "shipto",
        shipto_code,
    )

    # ── Call EDIFACT builder ──────────────────────────────────────────────
    try:
        from src.edifact_builder import build_orders_message, generate_tst_filename
        order_dict = {
            "order_number":   po_number,
            "order_date":     order_date,
            "delivery_date":  delivery_date,
        }
        edi_msg = build_orders_message(order_dict, resolved_lines, soldto_row, shipto_row)
    except Exception as e:
        _add_audit(cid, "edifact_generation_failed", actor, {"error": str(e)}, "FAILED")
        return JSONResponse(status_code=422, content={
            "conversion_id": cid, "status": "FAILED",
            "generated": False, "error": str(e)
        })

    # ── 11-point checklist ────────────────────────────────────────────────
    checks = _run_edi_checklist(edi_msg)
    all_required_pass = all(c["ok"] for c in checks if c["required"])
    new_status = "ACCEPTED" if all_required_pass else "REVIEW_REQUIRED"
    delivery_status = "READY_FOR_DOWNLOAD" if all_required_pass else "NOT_APPLICABLE"

    # ── Write .tst ────────────────────────────────────────────────────────
    tst_fname = generate_tst_filename(po_number, soldto_code)
    tst_path  = Path(OUTBOX_DIR) / tst_fname
    try:
        tst_path.write_text(edi_msg, encoding="utf-8")
    except Exception as e:
        log.warning("Could not write .tst to outbox: %s", e)
        # Store in-memory only
        tst_path = None

    # ── Update conversion in DB ───────────────────────────────────────────
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute("""
            UPDATE conversions SET
                status=?, delivery_status=?, tst_filename=?,
                edifact_content=?, po_number=?, soldto=?, shipto=?,
                corrections_json=?, updated_at=datetime('now')
            WHERE id=?""",
            [new_status, delivery_status, tst_fname,
             edi_msg, po_number, soldto_code, shipto_code,
             _json.dumps(cor), cid])
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("DB update after generate failed: %s", e)

    # ── Audit ─────────────────────────────────────────────────────────────
    _add_audit(cid, "edifact_regenerated_from_review", actor, {
        "po_number": po_number, "soldto": soldto_code, "shipto": shipto_code,
        "line_count": len(resolved_lines), "skipped": len(skipped_lines),
        "tst_filename": tst_fname, "checklist_passed": all_required_pass,
    }, new_status)

    return {
        "conversion_id":   cid,
        "status":          new_status,
        "business_status": "ACCEPTED" if all_required_pass else "REVIEW_REQUIRED",
        "delivery_status": delivery_status,
        "tst_filename":    tst_fname,
        "download_url":    f"/api/download/{tst_fname}",
        "edifact_content": edi_msg,
        "validation_checks": checks,
        "line_count":      len(resolved_lines),
        "skipped_lines":   len(skipped_lines),
        "generated":       True,
    }


@app.post("/api/conversions/{cid}/retry-sftp")
async def api_retry_sftp(cid: str):
    """Retry SFTP send for a conversion that previously failed."""
    return await api_send_sftp(cid)


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.get("/api/dashboard")
def api_dashboard():
    """KPIs + work queue for the cockpit page."""
    _init_db()
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        # Status counts today
        rows = conn.execute("""
          SELECT status, COUNT(*) as n FROM conversions
          WHERE date(created_at) = date('now') GROUP BY status
        """).fetchall()
        today = {r[0]: r[1] for r in rows}
        # Total counts
        total_rows = conn.execute(
            "SELECT status, COUNT(*) FROM conversions GROUP BY status"
        ).fetchall()
        totals = {r[0]: r[1] for r in total_rows}
        # Work queue: REVIEW_REQUIRED + recent FAILED + SFTP_FAILED
        queue = conn.execute("""
          SELECT id, source_filename, status, rejection_code, po_number, soldto, created_at
          FROM conversions WHERE status IN ('REVIEW_REQUIRED','SFTP_FAILED','EMAIL_FAILED','FAILED')
          ORDER BY created_at DESC LIMIT 20
        """).fetchall()
        queue_cols = ["id","source_filename","status","rejection_code","po_number","soldto","created_at"]
        conn.close()
        return {
            "today": today,
            "totals": totals,
            "work_queue": [dict(zip(queue_cols, r)) for r in queue],
        }
    except Exception as e:
        return {"today": {}, "totals": {}, "work_queue": [], "error": str(e)}


# ── Conversions list ──────────────────────────────────────────────────────────
@app.get("/api/conversions")
def api_conversions(status: str = "", q: str = "", limit: int = 100):
    """Return conversion history with optional status/text filter."""
    _init_db()
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        where, params = [], []
        if status:
            where.append("status = ?"); params.append(status)
        if q:
            where.append("(source_filename LIKE ? OR po_number LIKE ? OR soldto LIKE ? OR shipto LIKE ?)")
            params += [f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"]
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            f"SELECT id,correlation_id,source_filename,pdf_hash,status,business_status,"
            f"delivery_status,po_number,order_date,delivery_date,soldto,shipto,"
            f"customer_name,confidence,line_count,missing_material_count,"
            f"rejection_code,rejection_message,tst_filename,sftp_status,email_status,"
            f"operator,created_at,updated_at "
            f"FROM conversions {clause} ORDER BY created_at DESC LIMIT ?",
            params + [limit]
        ).fetchall()
        cols = ["id","correlation_id","source_filename","pdf_hash","status","business_status",
                "delivery_status","po_number","order_date","delivery_date","soldto","shipto",
                "customer_name","confidence","line_count","missing_material_count",
                "rejection_code","rejection_message","tst_filename","sftp_status","email_status",
                "operator","created_at","updated_at"]
        conn.close()
        return {"conversions": [dict(zip(cols, r)) for r in rows]}
    except Exception as e:
        return {"conversions": [], "error": str(e)}


# ── Single conversion detail ──────────────────────────────────────────────────
@app.get("/api/conversions/{cid}")
def api_conversion_detail(cid: str):
    """Return a single conversion with extraction JSON and audit events."""
    _init_db()
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        row = conn.execute(
            "SELECT *,extraction_json,corrections_json FROM conversions WHERE id=?", [cid]
        ).fetchone()
        if not row:
            conn.close()
            return JSONResponse(status_code=404, content={"error": "Conversion introuvable"})
        cols = [d[0] for d in conn.execute("SELECT * FROM conversions LIMIT 0").description or []]
        detail = dict(zip(cols, row))
        # Parse JSON fields
        for field in ("extraction_json", "corrections_json"):
            try:
                if detail.get(field):
                    detail[field] = _json.loads(detail[field])
            except Exception:
                pass
        events = conn.execute(
            "SELECT event_type,actor,payload,result,created_at FROM audit_events"
            " WHERE conversion_id=? ORDER BY created_at ASC", [cid]
        ).fetchall()
        conn.close()
        detail["audit_events"] = [
            {"event_type": e[0], "actor": e[1], "payload": e[2], "result": e[3], "created_at": e[4]}
            for e in events
        ]
        return detail
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Approve ───────────────────────────────────────────────────────────────────
@app.post("/api/conversions/{cid}/approve")
async def api_approve(cid: str, req: Request):
    """Operator approves a REVIEW_REQUIRED conversion — marks it ACCEPTED."""
    try:
        request = await req.json()
    except Exception:
        request = {}
    actor, _ = _ensure_can_mutate(req, request)
    _init_db()
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute(
            "UPDATE conversions SET status='ACCEPTED',delivery_status='READY_FOR_DOWNLOAD',"
            "operator=?,corrections_json=?,updated_at=datetime('now') WHERE id=?",
            [actor,
             _json.dumps(request.get("corrections",{})), cid]
        )
        conn.commit(); conn.close()
        _add_audit(cid, "user_approved", actor,
                   request, "ACCEPTED")
        _emit_conversion_callback(cid, "user_approved", actor, request)
        return {"ok": True, "status": "ACCEPTED"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Reject ────────────────────────────────────────────────────────────────────
@app.post("/api/conversions/{cid}/reject")
async def api_reject(cid: str, req: Request):
    """Operator manually rejects a conversion."""
    try:
        request = await req.json()
    except Exception:
        request = {}
    actor, _ = _ensure_can_mutate(req, request)
    _init_db()
    try:
        code = request.get("rejection_code","MANUAL_REJECTION")
        msg  = request.get("rejection_message") or REJECT_LABELS.get(code,code)
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute(
            "UPDATE conversions SET status='REJECTED',rejection_code=?,rejection_message=?,"
            "operator=?,updated_at=datetime('now') WHERE id=?",
            [code, msg, actor, cid]
        )
        conn.commit(); conn.close()
        _add_audit(cid, "user_rejected", actor,
                   request, "REJECTED")
        _emit_conversion_callback(cid, "user_rejected", actor, request)
        return {"ok": True, "status": "REJECTED"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Save corrections ──────────────────────────────────────────────────────────
@app.post("/api/conversions/{cid}/review")
async def api_save_review(cid: str, req: Request):
    """Save operator corrections — keeps REVIEW_REQUIRED status."""
    try:
        request = await req.json()
    except Exception:
        request = {}
    actor, _ = _ensure_can_mutate(req, request)
    _init_db()
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute(
            "UPDATE conversions SET corrections_json=?,operator=?,"
            "po_number=COALESCE(?,po_number),updated_at=datetime('now') WHERE id=?",
            [_json.dumps(request.get("corrections",{})),
             actor,
             request.get("po_number"), cid]
        )
        conn.commit(); conn.close()
        _add_audit(cid, "user_corrected", actor, request)
        _emit_conversion_callback(cid, "user_corrected", actor, request)
        return {"ok": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Audit trail ───────────────────────────────────────────────────────────────
@app.get("/api/conversions/{cid}/audit")
def api_audit(cid: str):
    """Return audit events for a conversion."""
    _init_db()
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        events = conn.execute(
            "SELECT event_type,actor,payload,result,created_at "
            "FROM audit_events WHERE conversion_id=? ORDER BY created_at ASC", [cid]
        ).fetchall()
        conn.close()
        return {"events": [
            {"event_type": e[0],"actor": e[1],"payload": e[2],"result": e[3],"created_at": e[4]}
            for e in events
        ]}
    except Exception as e:
        return {"events": [], "error": str(e)}


# ── Send SFTP ─────────────────────────────────────────────────────────────────
@app.get("/api/sftp/status")
def api_sftp_status():
    """Return SFTP configuration state (no secrets)."""
    host     = os.environ.get("SFTP_HOST","")
    user     = os.environ.get("SFTP_USERNAME","")
    rdir     = os.environ.get("SFTP_REMOTE_DIR","")
    configured = bool(host and user)
    return {
        "configured": configured,
        "host": host or None,
        "username": user or None,
        "remote_dir": rdir or None,
        "auth_mode": "password" if os.environ.get("SFTP_PASSWORD") else "key",
    }


@app.post("/api/conversions/{cid}/send-sftp")
def api_send_sftp(cid: str, req: Request):
    """Send the .tst file for this conversion via SFTP."""
    _init_db()
    actor, _ = _ensure_can_mutate(req)
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        row = conn.execute(
            "SELECT tst_filename,edifact_content FROM conversions WHERE id=?", [cid]
        ).fetchone()
        if not row or not row[0]:
            conn.close()
            return JSONResponse(status_code=404, content={"error": "Aucun .tst pour cette conversion"})
        tst_filename, edifact_content = row
        conn.close()
        # Write to outbox if needed
        tst_path = Path(OUTBOX_DIR) / tst_filename
        if edifact_content and not tst_path.exists():
            tst_path.write_text(edifact_content, encoding="utf-8")
        ok, msg = _test_sftp()  # quick connectivity test
        if not ok:
            _upsert_sftp_status(cid, "SFTP_FAILED", msg)
            _add_audit(cid, "sftp_failed", actor, {"tst_filename": tst_filename}, msg)
            _emit_conversion_callback(cid, "sftp_failed", actor, {"tst_filename": tst_filename, "error": msg})
            return {"ok": False, "error": msg}
        # Use paramiko to upload
        try:
            import paramiko as _pm
            sftp_host = os.environ["SFTP_HOST"]
            sftp_user = os.environ["SFTP_USERNAME"]
            sftp_pass = os.environ.get("SFTP_PASSWORD","")
            sftp_dir  = os.environ.get("SFTP_REMOTE_DIR","/")
            client = _pm.SSHClient()
            client.set_missing_host_key_policy(_pm.AutoAddPolicy())
            client.connect(sftp_host, username=sftp_user, password=sftp_pass, timeout=15)
            sftp = client.open_sftp()
            remote = f"{sftp_dir.rstrip('/')}/{tst_filename}"
            sftp.put(str(tst_path), remote)
            sftp.close(); client.close()
            _upsert_sftp_status(cid, "SFTP_DELIVERED", remote)
            _add_audit(cid, "sftp_sent", actor, {"remote": remote}, "SFTP_DELIVERED")
            _emit_conversion_callback(cid, "sftp_sent", actor, {"remote": remote})
            return {"ok": True, "remote_path": remote}
        except Exception as e:
            _upsert_sftp_status(cid, "SFTP_FAILED", str(e))
            _add_audit(cid, "sftp_failed", actor, {}, str(e))
            _emit_conversion_callback(cid, "sftp_failed", actor, {"error": str(e)})
            return {"ok": False, "error": str(e)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


def _upsert_sftp_status(cid: str, sftp_status: str, detail: str = "") -> None:
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute(
            "UPDATE conversions SET sftp_status=?,updated_at=datetime('now') WHERE id=?",
            [sftp_status, cid]
        )
        conn.commit(); conn.close()
    except Exception: pass


# ── Rejection email preview ───────────────────────────────────────────────────
@app.post("/api/notifications/preview-rejection")
async def api_preview_rejection_endpoint(req: Request):
    """Generate rejection email body (FR + EN) without sending."""
    try:
        request = await req.json()
    except Exception:
        request = {}
    cid        = request.get("conversion_id","?")
    filename   = request.get("source_filename","—")
    po_number  = request.get("po_number","INCONNU")
    code       = request.get("rejection_code","?")
    message    = request.get("rejection_message") or REJECT_LABELS.get(code, code)
    details    = request.get("details","")
    received   = request.get("received_at") or __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject_fr = f"[File2EDI][REJET][{code}] Commande {po_number} - {filename}"
    body_fr = f"""Bonjour,

La commande ci-dessous n'a pas pu être traitée automatiquement par File2EDI.

Fichier         : {filename}
N° commande     : {po_number}
Date réception  : {received}
Code rejet      : {code}
Motif           : {message}
Correlation ID  : {cid}

Détails :
{details or 'Aucun détail supplémentaire.'}

Action requise :
Merci de vérifier la commande et de corriger les données si nécessaire.

Cordialement,
File2EDI — EDIFACT Generator
"""
    subject_en = f"Your Order {po_number} was rejected"
    body_en = f"""Dear Sir or Madam,

Your order {po_number} was received on {received} but could not be processed in our system.

Reason: {message}

We are therefore returning your document in the attachment.

Best Regards,
File2EDI / EDIFACT Generator
"""
    return {
        "subject_fr": subject_fr,
        "body_fr": body_fr,
        "subject_en": subject_en,
        "body_en": body_en,
        "rejection_mailbox": "botrejet.Commandes@fr.bosch.com",
    }


@app.post("/api/conversions/{cid}/send-rejection-email")
async def api_send_rejection_email(cid: str, req: Request):
    """Send rejection email. Returns EMAIL_NOT_CONFIGURED if no transport."""
    try:
        request = await req.json()
    except Exception:
        request = {}
    actor, _ = _ensure_can_mutate(req, request)
    _init_db()
    smtp_host = os.environ.get("SMTP_HOST","")
    if not smtp_host:
        return {"ok": False, "status": "EMAIL_NOT_CONFIGURED",
                "message": "Transport SMTP non configuré. Utilisez le bouton Copier pour envoyer manuellement."}
    try:
        import smtplib
        from email.mime.text import MIMEText
        preview = _build_rejection_preview(request)
        msg = MIMEText(request.get("body") or preview["body_fr"])
        msg["Subject"] = request.get("subject") or preview["subject_fr"]
        msg["From"]    = os.environ.get("SMTP_FROM","file2edi@fr.bosch.com")
        msg["To"]      = request.get("to","botrejet.Commandes@fr.bosch.com")
        with smtplib.SMTP(smtp_host, int(os.environ.get("SMTP_PORT",25))) as server:
            server.sendmail(msg["From"], [msg["To"]], msg.as_string())
        # Update email_status
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute(
            "UPDATE conversions SET email_status='EMAIL_SENT',updated_at=datetime('now') WHERE id=?",
            [cid]
        )
        conn.commit(); conn.close()
        _add_audit(cid, "rejection_email_sent", actor, request, "EMAIL_SENT")
        return {"ok": True, "status": "EMAIL_SENT"}
    except Exception as e:
        _add_audit(cid, "rejection_email_failed", actor, {}, str(e))
        return {"ok": False, "status": "EMAIL_FAILED", "error": str(e)}


# ── Masterdata search ─────────────────────────────────────────────────────────
@app.get("/api/masterdata/customers/search")
def api_md_customers(q: str = "", limit: int = 50):
    return {"results": _csv_search_cached("customers", q, min(limit, 200))}

@app.get("/api/masterdata/partners/search")
def api_md_partners(q: str = "", limit: int = 50):
    return {"results": _csv_search_cached("partners", q, min(limit, 200))}

@app.get("/api/masterdata/materials/search")
def api_md_materials(q: str = "", limit: int = 50):
    return {"results": _csv_search_cached("materials", q, min(limit, 200))}

@app.get("/api/masterdata/salesorders/search")
def api_md_salesorders(q: str = "", limit: int = 50):
    return {"results": _csv_search_cached("salesorders", q, min(limit, 200))}


@app.post("/api/masterdata/reload-cache")
def api_md_reload_cache():
    """Force reload of all masterdata caches (Req 13)."""
    _load_masterdata_cache()
    stats = _masterdata_stats()
    return {
        "status": "ok",
        "schema_summary": {
            k: {
                "valid":   v.get("schema_valid"),
                "rows":    v.get("rows", 0),
                "missing": v.get("missing_columns", []),
                "source":  v.get("source", "?"),
            }
            for k, v in stats.items()
        },
    }


@app.get("/api/masterdata/diagnostics")
def api_md_diagnostics():
    """Comprehensive masterdata diagnostics for Paramètres > Diagnostics (Req 6+13)."""
    stats = _masterdata_stats()
    return {
        "active_source":     {k: _MD_SOURCE.get(k, "unknown") for k in _MD_FILES},
        "last_sync":         dict(_MD_LAST_SYNC),
        "files":             stats,
        "full_load_warning": (
            "Les fichiers masterdata sont traités comme full-load. "
            "Aucune suppression automatique n'est exécutée par File2EDI."
        ),
        "cache_ready": all(v.get("rows", 0) > 0 for v in stats.values()),
        "all_valid":   all(v.get("schema_valid", True) is not False for v in stats.values()),
    }

@app.post("/api/conversions/{cid}/audit")
async def api_add_audit_event(cid: str, req: Request):
    """Lightweight operator audit event (user_selected_soldto, user_corrected_article, etc.)."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    actor, _ = _ensure_can_mutate(req, body)
    save_audit_event(
        cid,
        body.get("event_type", "operator_action"),
        actor,
        body.get("payload"),
        body.get("result"),
    )
    return {"ok": True}


@app.get("/api/notifications/templates")
def api_notification_templates():
    return {
        "templates": [
            {"code": "REJECTION_FR", "language": "fr", "subject": "[File2EDI][REJET][{code}] Commande {po} - {file}"},
            {"code": "REJECTION_EN", "language": "en", "subject": "Your Order {po} was rejected"},
        ],
        "rejection_mailbox": "botrejet.Commandes@fr.bosch.com",
        "email_configured": bool(os.environ.get("SMTP_HOST","")),
    }


@app.get("/", response_class=HTMLResponse)
def spa_root():
    return _spa_index_response()


def _spa_index_response() -> HTMLResponse:
    if INDEX_HTML.exists():
        return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<h2>Frontend building... Run: cd frontend && npm run build</h2>",
        status_code=503,
    )

# Mount Vite assets (/assets/*)
if STATIC_DIR.exists():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


@app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
def spa_fallback(full_path: str):
    """React Router paths (/revue, /convertir, …) — serve index.html on direct URL access."""
    if full_path.startswith(("api/", "assets/")):
        raise HTTPException(404)
    return _spa_index_response()


# ── Dev entry ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("DATABRICKS_APP_PORT", 8000)))
