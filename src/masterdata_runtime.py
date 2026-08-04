"""Masterdata runtime cache, search, and SPA payload helpers.

Pure domain module (no FastAPI Request, no server/store imports).
Request-scoped auth filtering is applied by server wrappers that pass
``allowed_soldtos``.
"""

from __future__ import annotations

import csv as _csv
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("edifact.masterdata_runtime")

MASTER_FILES = [
    "10564_Customers.csv",
    "10564_Partners.csv",
    "10564_Materials.csv",
    "DB_Salesorder.csv",
]

MD_FILES = {
    "customers": "10564_Customers.csv",
    "partners": "10564_Partners.csv",
    "materials": "10564_Materials.csv",
    "salesorders": "DB_Salesorder.csv",
}

MD_SEARCH_COLS = {
    "customers": ["SOLDTO", "NAME", "ORT01", "PSTLZ", "STRAS", "LAND1", "VAT_NR"],
    "partners": ["SOLDTO", "SHIPTO", "NAME", "ORT01", "PSTLZ", "STRAS", "PARVW"],
    "materials": ["MATNR", "MAKTX"],
    "salesorders": ["BSTNK", "VBELN", "KUNNR", "ERDAT", "BSTDK", "ERNAM"],
}

MD_REQUIRED_COLS: dict[str, list[str]] = {
    "customers": ["SOLDTO", "NAME", "ORT01", "PSTLZ", "STRAS", "LAND1", "VAT_NR"],
    "partners": ["SOLDTO", "SHIPTO", "LAND1", "NAME", "ORT01", "PSTLZ", "STRAS", "PARVW"],
    "materials": ["MATNR", "MAKTX"],
    "salesorders": ["VBELN", "ERDAT", "ERNAM", "BSTNK", "BSTDK", "KUNNR"],
}

CACHE: dict[str, Any] = {}
_MC_LOCK = threading.Lock()
MD_SOURCE: dict[str, str] = {}
MD_LAST_SYNC: dict[str, str] = {}

_CFG: dict[str, Any] = {
    "runtime_dir": "",
    "source_dir": "",
    "metadata_path": "",
    "metadata_filename": ".masterdata_sync_metadata.json",
    "stale_hours": 25,
}


def configure(
    *,
    runtime_dir: str,
    source_dir: str = "",
    metadata_path: str = "",
    metadata_filename: str = ".masterdata_sync_metadata.json",
    stale_hours: int = 25,
) -> None:
    """Bind runtime paths from the application entrypoint."""
    _CFG["runtime_dir"] = str(runtime_dir)
    _CFG["source_dir"] = str(source_dir or "")
    _CFG["metadata_filename"] = metadata_filename or ".masterdata_sync_metadata.json"
    _CFG["metadata_path"] = str(
        metadata_path
        or (Path(runtime_dir) / _CFG["metadata_filename"])
    )
    try:
        _CFG["stale_hours"] = int(stale_hours)
    except Exception:
        _CFG["stale_hours"] = 25


def runtime_dir() -> Path:
    raw = _CFG.get("runtime_dir") or os.environ.get("MASTERDATA_RUNTIME_DIR") or "data/masterdata"
    return Path(str(raw))


def _display_name_from_actor(actor: str) -> str:
    normalized = (actor or "").strip().lower()
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


def normalize_value(s: str) -> str:
    return " ".join(str(s).strip().upper().split())


def normalize_vat(vat: str) -> str:
    return "".join(c for c in str(vat).upper() if c.isalnum())


def normalize_postal(postal: str) -> str:
    return "".join(c for c in str(postal).strip() if c.isalnum()).upper()


def normalize_city(city: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", str(city).strip().upper())
    return " ".join(s.split())


def normalize_article_code(art: str) -> str:
    s = str(art).strip().upper()
    if s.isdigit():
        s = str(int(s))
    return s


def validate_schema(key: str, df) -> dict:
    required = MD_REQUIRED_COLS.get(key, [])
    present = list(df.columns) if df is not None else []
    missing = [c for c in required if c not in present]
    return {
        "required_columns": required,
        "present_columns": present,
        "missing_columns": missing,
        "schema_valid": len(missing) == 0,
    }


def read_sync_metadata() -> dict:
    candidates = [
        Path(str(_CFG.get("metadata_path") or "")),
        runtime_dir() / str(_CFG.get("metadata_filename") or ".masterdata_sync_metadata.json"),
    ]
    source = str(_CFG.get("source_dir") or "").strip()
    if source:
        candidates.append(Path(source) / str(_CFG.get("metadata_filename") or ".masterdata_sync_metadata.json"))
    seen: set[str] = set()
    for p in candidates:
        k = str(p)
        if not k or k in seen:
            continue
        seen.add(k)
        if not p.exists() or not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["_metadata_path"] = str(p)
                return data
        except Exception as exc:
            log.warning("masterdata sync metadata parse failed (%s): %s", p, exc)
    return {}


def sync_freshness() -> dict:
    meta = read_sync_metadata()
    sync_at = str(meta.get("synced_at_utc") or meta.get("synced_at") or "").strip()
    stale_hours = float(_CFG.get("stale_hours") or 25)
    age_hours: float | None = None
    stale = None
    if sync_at:
        try:
            sync_dt = datetime.fromisoformat(sync_at.replace("Z", "+00:00"))
            age_hours = round(
                (datetime.now(timezone.utc) - sync_dt.astimezone(timezone.utc)).total_seconds() / 3600,
                2,
            )
            stale = age_hours > stale_hours
        except Exception:
            stale = None
    if not sync_at:
        status = "unknown"
    elif stale is True:
        status = "stale"
    elif stale is False:
        status = "fresh"
    else:
        status = "unknown"
    return {
        "status": status,
        "stale": stale,
        "stale_after_hours": int(stale_hours),
        "synced_at_utc": sync_at or None,
        "age_hours": age_hours,
        "repo_url": meta.get("repo_url"),
        "branch": meta.get("branch"),
        "commit": meta.get("commit"),
        "files": meta.get("files") if isinstance(meta.get("files"), dict) else {},
        "metadata_path": meta.get("_metadata_path"),
    }


def apply_sync_metadata_to_cache_state() -> None:
    meta = read_sync_metadata()
    sync_at = str(meta.get("synced_at_utc") or meta.get("synced_at") or "").strip()
    if not sync_at:
        return
    for key in MD_FILES:
        MD_LAST_SYNC.setdefault(key, sync_at)


def stats() -> dict:
    result: dict[str, dict] = {}
    for key, fname in MD_FILES.items():
        entry = CACHE.get(key)
        if entry and (entry.get("rows", 0) > 0 or entry.get("error")):
            if entry.get("error") and not entry.get("rows", 0):
                status = "ERROR"
            elif entry.get("rows", 0) == 0:
                status = "EMPTY"
            elif entry.get("schema_valid") is False:
                status = "SCHEMA_INVALID"
            else:
                status = "OK"
            result[key] = {
                "file": fname,
                "status": status,
                "rows": entry.get("rows", 0),
                "required_columns": entry.get("required_columns", MD_REQUIRED_COLS.get(key, [])),
                "present_columns": entry.get("present_columns", []),
                "missing_columns": entry.get("missing_columns", []),
                "source": entry.get("source", "bundled"),
                "loaded_at": entry.get("loaded_at"),
                "file_size_kb": entry.get("file_size_kb", 0.0),
                "schema_valid": entry.get("schema_valid"),
                "warnings": entry.get("warnings", []),
            }
        else:
            fp = runtime_dir() / fname
            if not fp.exists():
                result[key] = {
                    "file": fname, "status": "MISSING", "rows": 0,
                    "required_columns": MD_REQUIRED_COLS.get(key, []),
                    "present_columns": [], "missing_columns": MD_REQUIRED_COLS.get(key, []),
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
                        "required_columns": MD_REQUIRED_COLS.get(key, []),
                        "present_columns": [], "missing_columns": [],
                        "source": "bundled", "loaded_at": None,
                        "file_size_kb": round(fp.stat().st_size / 1024, 1),
                        "schema_valid": None,
                        "warnings": ["Cache non chargé — rechargement recommandé."],
                    }
                except Exception as exc:
                    result[key] = {
                        "file": fname, "status": "ERROR", "rows": 0,
                        "required_columns": MD_REQUIRED_COLS.get(key, []),
                        "present_columns": [], "missing_columns": [],
                        "source": "error", "loaded_at": None, "file_size_kb": 0.0,
                        "schema_valid": False, "warnings": [str(exc)],
                    }
    return result


def csv_search(csv_name: str, q: str, cols: list[str], limit: int = 50) -> list[dict]:
    q_lo = q.strip().lower()
    results: list[dict] = []
    try:
        fpath = runtime_dir() / csv_name
        with open(fpath, encoding="utf-8", newline="") as f:
            reader = _csv.DictReader(f, delimiter=";")
            for row in reader:
                haystack = " ".join(str(row.get(c, "")) for c in cols).lower()
                if not q_lo or q_lo in haystack:
                    results.append(dict(row))
                    if len(results) >= limit:
                        break
    except Exception as e:
        log.warning("csv_search(%s): %s", csv_name, e)
    return results


def load_cache() -> dict:
    try:
        import pandas as _pd
    except ImportError:
        log.warning("pandas not available — masterdata cache disabled")
        return {"error": "pandas not available"}

    with _MC_LOCK:
        for key, fname in MD_FILES.items():
            fpath = runtime_dir() / fname
            src_type = "workspace" if key in MD_LAST_SYNC else "bundled"
            prev_entry = CACHE.get(key)
            try:
                df = _pd.read_csv(
                    str(fpath), sep=";", dtype=str,
                    keep_default_na=False, on_bad_lines="skip",
                    encoding="utf-8", encoding_errors="replace",
                )
                df.columns = [c.strip() for c in df.columns]
                schema_info = validate_schema(key, df)
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
                CACHE[key] = {
                    "df": df,
                    "rows": len(df),
                    "loaded_at": datetime.now().isoformat(timespec="seconds"),
                    "error": None,
                    "fname": fname,
                    "source": src_type,
                    "source_path": str(fpath),
                    "file_size_kb": fsize_kb,
                    "schema_valid": schema_info["schema_valid"],
                    "required_columns": schema_info["required_columns"],
                    "present_columns": schema_info["present_columns"],
                    "missing_columns": schema_info["missing_columns"],
                    "warnings": warnings,
                }
                MD_SOURCE[key] = src_type
                log.info(
                    "MD cache: %s — %d rows  schema_valid=%s  source=%s",
                    fname, len(df), schema_info["schema_valid"], src_type,
                )
            except FileNotFoundError:
                if prev_entry and prev_entry.get("df") is not None:
                    fallback = dict(prev_entry)
                    fallback["source"] = "fallback"
                    fallback["warnings"] = list(prev_entry.get("warnings", [])) + [
                        f"Fichier introuvable: {fpath} — données précédentes conservées."
                    ]
                    CACHE[key] = fallback
                    MD_SOURCE[key] = "fallback"
                    log.warning("MD cache: %s MISSING — Tier C fallback active", fname)
                else:
                    CACHE[key] = {
                        "df": None, "rows": 0, "loaded_at": None,
                        "error": f"Fichier introuvable: {fpath}",
                        "fname": fname, "source": "error",
                        "schema_valid": False,
                        "required_columns": MD_REQUIRED_COLS.get(key, []),
                        "present_columns": [], "missing_columns": [], "warnings": [],
                    }
                    MD_SOURCE[key] = "error"
                    log.warning("MD cache load failed (%s): file not found", fname)
            except Exception as exc:
                if prev_entry and prev_entry.get("df") is not None:
                    fallback = dict(prev_entry)
                    fallback["source"] = "fallback"
                    fallback["warnings"] = list(prev_entry.get("warnings", [])) + [
                        f"Erreur rechargement: {exc} — données précédentes conservées."
                    ]
                    CACHE[key] = fallback
                    MD_SOURCE[key] = "fallback"
                    log.warning("MD cache: %s ERROR — Tier C fallback: %s", fname, exc)
                else:
                    CACHE[key] = {
                        "df": None, "rows": 0, "loaded_at": None, "error": str(exc),
                        "fname": fname, "source": "error",
                        "schema_valid": False,
                        "required_columns": MD_REQUIRED_COLS.get(key, []),
                        "present_columns": [], "missing_columns": [], "warnings": [],
                    }
                    MD_SOURCE[key] = "error"
                    log.warning("MD cache load failed (%s): %s", fname, exc)

    return {k: {"rows": v["rows"], "loaded_at": v["loaded_at"], "error": v.get("error")}
            for k, v in CACHE.items()}


def refresh_cache() -> None:
    load_cache()


def table_records(key: str) -> list[dict]:
    entry = CACHE.get(key, {})
    df = entry.get("df")
    if df is not None:
        try:
            return [dict(row) for row in df.to_dict("records")]
        except Exception:
            pass
    fname = MD_FILES.get(key, "")
    if not fname:
        return []
    path = runtime_dir() / fname
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            return [dict(row) for row in _csv.DictReader(fh, delimiter=";")]
    except Exception:
        return []


def row_value(row: dict, *names: str) -> str:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        value = lowered.get(str(name).strip().lower())
        if value is not None:
            return str(value).strip()
    return ""


def match_keys(value: str) -> set[str]:
    raw = (value or "").strip()
    if not raw:
        return set()
    variants = {raw}
    local = raw.split("@", 1)[0]
    variants.add(local)
    variants.add(re.sub(r"[._-]+", " ", local))
    variants.add(_display_name_from_actor(raw))
    keys: set[str] = set()
    for variant in variants:
        cleaned = (variant or "").strip()
        if not cleaned:
            continue
        norm = normalize_value(cleaned)
        keys.add(norm)
        keys.add(norm.replace(" ", ""))
        parts = [part for part in re.split(r"[^A-Z0-9]+", norm) if part]
        if parts:
            keys.add(" ".join(sorted(parts)))
    return {key for key in keys if key}


def row_matches_actor(row: dict, actor_keys: set[str]) -> bool:
    if not actor_keys:
        return False
    for field in (
        "adv_team1_email",
        "adv_team2_email",
        "email",
        "gestionaire_adv",
        "Gestionaire ADV",
    ):
        raw = row_value(row, field)
        if not raw:
            continue
        for chunk in re.split(r"[;,|/]+", raw):
            if match_keys(chunk) & actor_keys:
                return True
    return False


def csv_search_cached(
    key: str,
    q: str,
    limit: int = 50,
    allowed_soldtos: set[str] | None = None,
) -> list[dict]:
    """Search cache. ``allowed_soldtos=None`` means unrestricted."""
    limit = min(int(limit or 50), 200)
    entry = CACHE.get(key, {})
    df = entry.get("df")
    cols = MD_SEARCH_COLS.get(key, [])
    q_lo = q.strip().lower()

    if df is None:
        rows = csv_search(MD_FILES.get(key, ""), q, cols, limit)
        if allowed_soldtos is None or key not in {"customers", "partners"}:
            return rows
        if not allowed_soldtos:
            return []
        return [
            row for row in rows
            if row_value(row, "SOLDTO", "soldto") in allowed_soldtos
        ][:limit]

    if allowed_soldtos is not None and key in {"customers", "partners"}:
        if not allowed_soldtos:
            return []
        soldto_col = next((c for c in df.columns if str(c).strip().lower() == "soldto"), None)
        if soldto_col is not None:
            df = df[df[soldto_col].astype(str).str.strip().isin(allowed_soldtos)]

    if not q_lo:
        return df.head(limit).to_dict("records")

    safe_cols = [c for c in cols if c in df.columns]
    if not safe_cols:
        return df.head(limit).to_dict("records")

    mask = df[safe_cols].apply(
        lambda c: c.str.lower().str.contains(q_lo, na=False)
    ).any(axis=1)
    return df[mask].head(limit).to_dict("records")


def visible_records(key: str, allowed_soldtos: set[str] | None) -> list[dict]:
    rows = table_records(key)
    if allowed_soldtos is None or key not in {"customers", "partners"}:
        return rows
    if not allowed_soldtos:
        return []
    return [row for row in rows if row_value(row, "SOLDTO", "soldto") in allowed_soldtos]


def format_clients(rows: list[dict], sync_at: str = "") -> list[dict]:
    clients: list[dict] = []
    for i, row in enumerate(rows):
        soldto = row_value(row, "SOLDTO", "soldto")
        clients.append({
            "clientId": soldto or f"cli-{i}",
            "name": row_value(row, "NAME", "name"),
            "soldto": soldto,
            "vat": row_value(row, "VAT_NR", "vat"),
            "channel": row_value(row, "VTWEG", "channel") or "—",
            "division": row_value(row, "SPART", "division") or "—",
            "status": "Actif",
            "updatedAt": sync_at,
            "country": row_value(row, "LAND1", "country"),
            "city": row_value(row, "ORT01", "city"),
            "postalCode": row_value(row, "PSTLZ", "postal", "postalCode"),
            "address": row_value(row, "STRAS", "address", "street"),
            "currency": "EUR",
            "fields": {str(k): str(v) if v is not None else "" for k, v in row.items()},
        })
    return clients


def format_partners(rows: list[dict], sync_at: str = "") -> list[dict]:
    out: list[dict] = []
    for i, row in enumerate(rows):
        shipto = row_value(row, "SHIPTO", "shipto")
        soldto = row_value(row, "SOLDTO", "soldto")
        out.append({
            "id": f"{soldto}:{shipto}" if soldto or shipto else f"st-{i}",
            "shipto": shipto,
            "soldto": soldto,
            "name": row_value(row, "NAME", "name"),
            "country": row_value(row, "LAND1", "country"),
            "city": row_value(row, "ORT01", "city"),
            "postalCode": row_value(row, "PSTLZ", "postal", "postalCode"),
            "address": row_value(row, "STRAS", "address", "street"),
            "partnerFunction": row_value(row, "PARVW", "partnerFunction"),
            "advManager": row_value(
                row, "Gestionaire ADV", "Gestionnaire ADV", "advManager", "ADV"
            ),
            "updatedAt": sync_at,
            "fields": {str(k): str(v) if v is not None else "" for k, v in row.items()},
        })
    return out


def format_materials(rows: list[dict], sync_at: str = "") -> list[dict]:
    out: list[dict] = []
    for i, row in enumerate(rows):
        matnr = row_value(row, "MATNR", "matnr", "material")
        out.append({
            "id": matnr or f"mat-{i}",
            "materialId": matnr,
            "description": row_value(row, "MAKTX", "maktx", "description"),
            "updatedAt": sync_at,
            "fields": {str(k): str(v) if v is not None else "" for k, v in row.items()},
        })
    return out


def format_rules(search: str = "") -> list[dict]:
    from src.rejection_catalog import REJECTION_CATALOG

    q = (search or "").strip().lower()
    out: list[dict] = []
    for code, entry in REJECTION_CATALOG.items():
        message = str(entry.get("message_fr") or "")
        severity = str(entry.get("severity") or "")
        if q and q not in code.lower() and q not in message.lower() and q not in severity.lower():
            continue
        out.append({
            "id": code,
            "code": code,
            "severity": severity,
            "businessStatus": entry.get("business_status") or "",
            "message": message,
            "retryAllowed": bool(entry.get("retry_allowed")),
            "manualReview": bool(entry.get("manual_review_required")),
            "fields": {
                "code": code,
                "severity": severity,
                "business_status": str(entry.get("business_status") or ""),
                "message_fr": message,
                "message_en": str(entry.get("message_en") or ""),
                "retry_allowed": str(bool(entry.get("retry_allowed"))),
                "manual_review_required": str(bool(entry.get("manual_review_required"))),
            },
        })
    return out


def summary_for_scope(allowed_soldtos: set[str] | None) -> dict:
    from src.rejection_catalog import REJECTION_CATALOG

    md_stats = stats()
    md_sync = sync_freshness()
    last_sync = (
        md_sync.get("synced_at_utc")
        or (max(MD_LAST_SYNC.values()) if MD_LAST_SYNC else "")
        or ""
    )
    rules_count = len(REJECTION_CATALOG)
    growth = {"clients": 0, "shipto": 0, "articles": 0, "rules": 0}
    if allowed_soldtos is None:
        return {
            "activeClients": md_stats.get("customers", {}).get("rows", 0),
            "shiptoCount": md_stats.get("partners", {}).get("rows", 0),
            "articlesCount": md_stats.get("materials", {}).get("rows", 0),
            "rulesCount": rules_count,
            "lastSync": last_sync,
            "syncStatus": md_sync.get("status"),
            "syncCommit": md_sync.get("commit"),
            "monthlyGrowth": growth,
        }
    return {
        "activeClients": len(visible_records("customers", allowed_soldtos)),
        "shiptoCount": len(visible_records("partners", allowed_soldtos)),
        "articlesCount": md_stats.get("materials", {}).get("rows", 0),
        "rulesCount": rules_count,
        "lastSync": last_sync,
        "syncStatus": md_sync.get("status"),
        "syncCommit": md_sync.get("commit"),
        "monthlyGrowth": growth,
    }


def payload_for_scope(
    allowed_soldtos: set[str] | None,
    type_name: str = "clients",
    search: str = "",
    limit: int = 100,
) -> dict:
    kind = (type_name or "clients").strip().lower()
    limit = min(max(int(limit or 100), 1), 200)
    summary = summary_for_scope(allowed_soldtos)
    sync_at = summary.get("lastSync") or ""

    if kind in {"shipto", "partners", "ship-to"}:
        rows = format_partners(
            csv_search_cached("partners", search, limit, allowed_soldtos),
            sync_at,
        )
        return {"summary": summary, "type": "shipto", "clients": [], "rows": rows}
    if kind in {"articles", "materials", "articles-bosch"}:
        rows = format_materials(csv_search_cached("materials", search, limit), sync_at)
        return {"summary": summary, "type": "articles", "clients": [], "rows": rows}
    if kind in {"rules", "regles", "validation"}:
        return {"summary": summary, "type": "rules", "clients": [], "rows": format_rules(search)}

    clients = format_clients(
        csv_search_cached("customers", search, limit, allowed_soldtos),
        sync_at,
    )
    return {"summary": summary, "type": "clients", "clients": clients, "rows": clients}


def kind_key(kind: str) -> str:
    mapping = {
        "clients": "customers",
        "customers": "customers",
        "shipto": "partners",
        "partners": "partners",
        "articles": "materials",
        "materials": "materials",
    }
    key = mapping.get((kind or "").strip().lower())
    if not key:
        raise ValueError(f"Type masterdata inconnu: {kind}")
    return key


def write_csv(key: str, df) -> None:
    fname = MD_FILES[key]
    path = runtime_dir() / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, sep=";", index=False, encoding="utf-8")
    tmp.replace(path)
    MD_LAST_SYNC[key] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    load_cache()


def import_dataframe(key: str, raw: bytes) -> dict:
    import pandas as _pd
    from io import StringIO

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    df = _pd.read_csv(
        StringIO(text),
        sep=";",
        dtype=str,
        keep_default_na=False,
        on_bad_lines="skip",
        encoding_errors="replace",
    )
    df.columns = [str(c).strip() for c in df.columns]
    schema = validate_schema(key, df)
    if not schema["schema_valid"]:
        missing = ", ".join(schema["missing_columns"])
        raise ValueError(f"Colonnes manquantes pour {key}: {missing}")
    if len(df) == 0:
        raise ValueError("Fichier CSV vide")
    write_csv(key, df)
    return {"kind": key, "rows": int(len(df)), "file": MD_FILES[key]}


def append_row(key: str, fields: dict) -> dict:
    import pandas as _pd

    required = MD_REQUIRED_COLS.get(key, [])
    normalized = {
        str(k).strip(): str(v).strip() if v is not None else ""
        for k, v in (fields or {}).items()
    }
    lowered = {k.lower(): v for k, v in normalized.items()}
    for col in required:
        if col not in normalized and col.lower() in lowered:
            normalized[col] = lowered[col.lower()]
    missing = [c for c in required if not normalized.get(c)]
    if missing:
        raise ValueError(f"Champs obligatoires manquants: {', '.join(missing)}")

    entry = CACHE.get(key, {})
    df = entry.get("df")
    if df is None:
        load_cache()
        df = CACHE.get(key, {}).get("df")
    if df is None:
        df = _pd.DataFrame(columns=required)

    row = {col: normalized.get(col, "") for col in df.columns}
    for col, val in normalized.items():
        if col not in row:
            row[col] = val
    df = _pd.concat([df, _pd.DataFrame([row])], ignore_index=True)
    write_csv(key, df)
    return {"kind": key, "rows": int(len(df)), "added": row}


def allowed_soldtos_for_actor(
    actor: str,
    role: str,
) -> set[str] | None:
    """None = unrestricted; empty set = ADV with no linked sold-tos."""
    if role != "adv":
        return None
    if not actor:
        return set()
    actor_keys = match_keys(actor)
    allowed: set[str] = set()
    for row in table_records("partners"):
        if not row_matches_actor(row, actor_keys):
            continue
        soldto = row_value(row, "SOLDTO", "soldto")
        if soldto:
            allowed.add(soldto)
    return allowed
