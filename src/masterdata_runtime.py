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
    "DB_Materials.csv",
    "DB_Salesorder.csv",
]

# Canonical runtime filenames (CSV). Import accepte aussi .parquet → écrit en CSV.
MD_FILES = {
    "customers": "10564_Customers.csv",
    "partners": "10564_Partners.csv",
    "materials": "DB_Materials.csv",
    "salesorders": "DB_Salesorder.csv",
}

# Noms attendus côté GitHub / Databricks (préférés pour sync légère).
MD_PARQUET_FILES = {
    "customers": "10564_Customers.parquet",
    "partners": "10564_Partners.parquet",
    "materials": "DB_Materials.parquet",
    "salesorders": "DB_Salesorder.parquet",
}

# Ancien export Materials (fallback lecture seule si DB_Materials absent).
_MD_MATERIALS_LEGACY = ("10564_Materials.parquet", "10564_Materials.csv")

MD_SEARCH_COLS = {
    "customers": ["SOLDTO", "NAME", "ORT01", "PSTLZ", "STRAS", "LAND1", "VAT_NR"],
    "partners": ["SOLDTO", "SHIPTO", "NAME", "ORT01", "PSTLZ", "STRAS", "PARVW"],
    "materials": ["MATNR", "MAKTX"],  # étendu dynamiquement aux colonnes présentes
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


def _materials_df_and_cols() -> tuple[Any, str | None, str | None, str | None, str | None]:
    entry = CACHE.get("materials") or {}
    df = entry.get("df")
    if df is None or getattr(df, "empty", True):
        return None, None, None, None, None
    cols = {str(c).strip().lower(): c for c in df.columns}
    matnr_col = cols.get("matnr")
    statut_col = next(
        (cols[k] for k in ("statut", "status", "replacement", "remplace_par", "remplacé_par") if k in cols),
        None,
    )
    vmsta_col = cols.get("vmsta")
    commentaire_col = next(
        (cols[k] for k in ("commentaire", "comment", "comments", "bemerkung") if k in cols),
        None,
    )
    return df, matnr_col, statut_col, vmsta_col, commentaire_col


def _statut_is_available(statut: str, vmsta: str = "") -> bool:
    label = (statut or "").strip().lower()
    if label in {"", "nan", "none", "null", "-", "n/a", "na"}:
        return vmsta.strip() not in {"92"}
    return label == "article disponible"


def _statut_is_no_sale(statut: str, vmsta: str = "") -> bool:
    label = (statut or "").strip().lower()
    if label == "no sale" or "no sale" in label:
        return True
    return (vmsta or "").strip() == "92"


def _statut_as_replacement_matnr(statut: str) -> str | None:
    """When ``Statut`` holds another MATNR, return that replacement code."""
    raw = (statut or "").strip()
    if not raw:
        return None
    lower = raw.lower()
    if lower in {"article disponible", "no sale"} or "no sale" in lower:
        return None
    digits = re.sub(r"\D", "", raw)
    compact = raw.replace(" ", "")
    if len(digits) >= 5 and len(digits) >= max(len(compact), 1) * 0.7:
        return normalize_article_code(digits) or digits
    if re.fullmatch(r"\d{5,18}", compact):
        return normalize_article_code(compact) or compact
    return None


def _parse_replacement_since(commentaire: str) -> str | None:
    """Extract replacement date from Materials ``Commentaire`` (often DD/MM/YYYY alone)."""
    text = str(commentaire or "").strip()
    if not text or text.lower() in {"nan", "none", "null", "-", "n/a", "na"}:
        return None
    m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b", text)
    if not m:
        return None
    day, month, year = m.group(1), m.group(2), m.group(3)
    if len(year) == 2:
        year = f"20{year}"
    return f"{int(day):02d}/{int(month):02d}/{year}"


def format_material_replacement_commentaire(
    *,
    replacement: str,
    commentaire: str = "",
    article: str = "",
) -> str:
    """Human-readable Materials comment for a replaced article."""
    repl = str(replacement or "").strip()
    if not repl:
        return str(commentaire or "").strip()
    existing = str(commentaire or "").strip()
    if re.search(r"remplac[ée]s?\s+depuis\s+le", existing, re.I):
        return existing
    since = _parse_replacement_since(existing)
    if since:
        return f"Cette référence a été remplacée depuis le {since} par {repl}"
    if existing and not _parse_replacement_since(existing) and not existing.isdigit():
        return f"Cette référence a été remplacée par {repl} ({existing})"
    return f"Cette référence a été remplacée par {repl}"


def _material_row_fields(code: str) -> tuple[str, str, str] | None:
    """Return ``(statut, vmsta, commentaire)`` for a normalized MATNR, or ``None`` if absent."""
    df, matnr_col, statut_col, vmsta_col, commentaire_col = _materials_df_and_cols()
    if df is None or matnr_col is None:
        return None
    try:
        series = df[matnr_col].astype(str).map(lambda v: normalize_article_code(v))
        matches = df.loc[series == code]
        if matches.empty:
            return None
        row = matches.iloc[0]
        statut = str(row[statut_col] or "").strip() if statut_col else ""
        vmsta = str(row[vmsta_col] or "").strip() if vmsta_col else ""
        commentaire = ""
        if commentaire_col:
            raw = row[commentaire_col]
            commentaire = "" if raw is None else str(raw).strip()
            if commentaire.lower() in {"nan", "none", "null"}:
                commentaire = ""
        return statut, vmsta, commentaire
    except Exception:
        return None


def _material_direct_status(code: str) -> dict[str, Any]:
    """Single-hop Materials status (no replacement chain resolution)."""
    if not code:
        return {
            "found": False,
            "kind": "missing",
            "matnr": "",
            "statut": None,
            "replacement": None,
            "replacement_since": None,
            "commentaire": None,
        }

    row_fields = _material_row_fields(code)
    if row_fields is None:
        return {
            "found": False,
            "kind": "missing",
            "matnr": code,
            "statut": None,
            "replacement": None,
            "replacement_since": None,
            "commentaire": None,
        }

    statut, vmsta, commentaire = row_fields
    since = _parse_replacement_since(commentaire)
    replacement = _statut_as_replacement_matnr(statut)
    if replacement and replacement != code:
        return {
            "found": True,
            "kind": "replacement",
            "matnr": code,
            "statut": statut,
            "replacement": replacement,
            "replacement_since": since,
            "commentaire": commentaire or None,
        }
    if _statut_is_no_sale(statut, vmsta):
        return {
            "found": True,
            "kind": "no_sale",
            "matnr": code,
            "statut": statut,
            "replacement": None,
            "replacement_since": None,
            "commentaire": commentaire or None,
        }
    if _statut_is_available(statut, vmsta):
        return {
            "found": True,
            "kind": "available",
            "matnr": code,
            "statut": statut,
            "replacement": None,
            "replacement_since": None,
            "commentaire": commentaire or None,
        }
    return {
        "found": True,
        "kind": "available",
        "matnr": code,
        "statut": statut,
        "replacement": None,
        "replacement_since": None,
        "commentaire": commentaire or None,
    }


def material_line_status(matnr: str) -> dict[str, Any]:
    """Evaluate Materials masterdata status for an order line article.

    Replacement chains in ``Statut`` are resolved (A→B→C) with cycle detection.

    Returns ``kind``:
    - ``missing`` - MATNR not in masterdata
    - ``available`` - ``Article disponible`` (no anomaly)
    - ``no_sale`` - article arrêté (`no sale` / VMSTA 92), including replacement target
    - ``replacement`` - resolved final reference MATNR in ``replacement``
    """
    code = normalize_article_code(matnr)
    if not code:
        return {
            "found": False,
            "kind": "missing",
            "matnr": "",
            "statut": None,
            "replacement": None,
        }

    direct = _material_direct_status(code)
    if direct["kind"] != "replacement":
        return direct

    since = direct.get("replacement_since")
    chain: list[str] = [code]
    visited: set[str] = {code}
    current = str(direct.get("replacement") or "").strip()
    max_hops = 25

    def _with_since(payload: dict[str, Any]) -> dict[str, Any]:
        out = dict(payload)
        out.setdefault("replacement_since", since)
        out.setdefault("commentaire", direct.get("commentaire"))
        return out

    for _ in range(max_hops):
        if not current:
            break
        if current in visited:
            return _with_since({
                "found": True,
                "kind": "replacement",
                "matnr": code,
                "statut": direct.get("statut"),
                "replacement": current,
                "replacement_chain": chain + [current],
                "replacement_cycle": True,
            })
        visited.add(current)
        chain.append(current)
        hop = _material_direct_status(current)
        if hop["kind"] == "replacement":
            nxt = str(hop.get("replacement") or "").strip()
            if nxt and nxt != current:
                current = nxt
                continue
        if hop["kind"] == "missing":
            return _with_since({
                "found": True,
                "kind": "replacement",
                "matnr": code,
                "statut": hop.get("statut"),
                "replacement": current,
                "replacement_chain": chain,
                "replacement_missing": True,
            })
        if hop["kind"] == "no_sale":
            return _with_since({
                "found": True,
                "kind": "no_sale",
                "matnr": code,
                "statut": hop.get("statut"),
                "replacement": current,
                "replacement_chain": chain,
                "via_replacement": True,
            })
        return _with_since({
            "found": True,
            "kind": "replacement",
            "matnr": code,
            "statut": hop.get("statut"),
            "replacement": current,
            "replacement_chain": chain,
        })

    return _with_since({
        "found": True,
        "kind": "replacement",
        "matnr": code,
        "statut": direct.get("statut"),
        "replacement": current or str(direct.get("replacement") or ""),
        "replacement_chain": chain,
        "replacement_cycle": True,
    })



def material_status_replacement(matnr: str) -> str | None:
    """Legacy helper: final replacement MATNR after chain resolution."""
    status = material_line_status(matnr)
    if status.get("kind") == "replacement" and not status.get("replacement_cycle"):
        repl = status.get("replacement")
        if repl and not status.get("replacement_missing"):
            return str(repl)
    return None


def format_material_status_anomaly_message(
    *,
    line_number: int | str | None,
    matnr: str,
    mat_status: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    """Build a line-level MATERIAL_STATUS_INVALID message from Articles masterdata."""
    art = str(matnr or "").strip()
    if not art:
        return None
    status = mat_status if mat_status is not None else material_line_status(art)
    kind = status.get("kind")
    if kind == "available":
        return None

    line_prefix = f"Ligne {line_number} : " if line_number is not None else ""
    chain = status.get("replacement_chain") or []
    final_ref = str(status.get("replacement") or "").strip()
    since = str(status.get("replacement_since") or "").strip()
    since_txt = f" depuis le {since}" if since else ""

    if kind == "missing":
        return {
            "severity": "error",
            "message": f"{line_prefix}référence {art} absente du référentiel Articles.",
        }
    if kind == "no_sale":
        if status.get("via_replacement") and final_ref:
            msg = (
                f"{line_prefix}la référence {art} a été remplacée{since_txt} par {final_ref}, "
                f"mais {final_ref} est arrêtée (plus commercialisée)."
            )
        else:
            msg = f"{line_prefix}la référence {art} est arrêtée (plus commercialisée)."
        return {"severity": "warning", "message": msg}
    if kind == "replacement":
        if status.get("replacement_cycle"):
            chain_txt = " → ".join(chain) if chain else art
            msg = (
                f"{line_prefix}chaîne de remplacement circulaire pour {art} ({chain_txt})."
            )
            return {"severity": "warning", "message": msg}
        if status.get("replacement_missing") and final_ref:
            msg = (
                f"{line_prefix}la référence {art} a été remplacée{since_txt} par {final_ref}, "
                f"mais {final_ref} est absent du référentiel Articles."
            )
            return {"severity": "error", "message": msg}
        if len(chain) > 2:
            via = " → ".join(chain[1:-1])
            msg = (
                f"{line_prefix}la référence {art} a été remplacée{since_txt} par {final_ref} "
                f"(via {via})."
            )
        else:
            msg = (
                f"{line_prefix}la référence {art} a été remplacée{since_txt} par {final_ref}."
            )
        return {"severity": "warning", "message": msg}
    return None


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
    mem_sync = max(MD_LAST_SYNC.values()) if MD_LAST_SYNC else ""
    # Prefer the newest timestamp between metadata file and in-memory sync markers.
    if mem_sync and (not sync_at or str(mem_sync) > str(sync_at)):
        sync_at = str(mem_sync)
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


def bump_sync_metadata(
    *,
    synced_at_utc: str | None = None,
    commit: str | None = None,
    source: str | None = None,
    files: dict | None = None,
    repo_url: str | None = None,
    branch: str | None = None,
) -> dict:
    """Update ``.masterdata_sync_metadata.json`` so the UI last-sync stamp advances."""
    meta = dict(read_sync_metadata() or {})
    meta.pop("_metadata_path", None)
    now = (synced_at_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")).strip()
    meta["synced_at_utc"] = now
    if commit:
        meta["commit"] = str(commit)
    if source:
        meta["sync_runner"] = str(source)
    if files is not None:
        meta["files"] = files
    if repo_url:
        meta["repo_url"] = str(repo_url)
    if branch:
        meta["branch"] = str(branch)

    path = runtime_dir() / str(_CFG.get("metadata_filename") or ".masterdata_sync_metadata.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    tmp.replace(path)

    for key in MD_FILES:
        MD_LAST_SYNC[key] = now
    return {**meta, "_metadata_path": str(path)}


def apply_sync_metadata_to_cache_state() -> None:
    meta = read_sync_metadata()
    sync_at = str(meta.get("synced_at_utc") or meta.get("synced_at") or "").strip()
    if not sync_at:
        return
    for key in MD_FILES:
        MD_LAST_SYNC.setdefault(key, sync_at)


def _parquet_engine_available() -> bool:
    try:
        import pyarrow  # noqa: F401
        return True
    except ImportError:
        try:
            import fastparquet  # noqa: F401
            return True
        except ImportError:
            return False


def resolve_source_path(key: str) -> Path:
    """Prefer Parquet in runtime dir when readable, else CSV (legacy / post-import)."""
    root = runtime_dir()
    parquet_name = MD_PARQUET_FILES.get(key)
    csv_name = MD_FILES.get(key, "")
    csv_path = root / csv_name if csv_name else root
    parquet_path = root / parquet_name if parquet_name else None

    if parquet_path and parquet_path.exists() and _parquet_engine_available():
        return parquet_path
    if csv_name and csv_path.exists():
        return csv_path
    if parquet_path and parquet_path.exists():
        return parquet_path
    # Materials: fall back to old 10564_Materials.* if DB_Materials not synced yet
    if key == "materials":
        for legacy in _MD_MATERIALS_LEGACY:
            legacy_path = root / legacy
            if legacy_path.exists():
                return legacy_path
    return csv_path


def _dataframe_as_str(df: Any) -> Any:
    """Normalize all columns to stripped strings for masterdata cache."""
    out = df.fillna("").astype(str)
    out.columns = [str(c).strip() for c in out.columns]
    for col in out.columns:
        out[col] = (
            out[col]
            .str.strip()
            .replace({"nan": "", "None": "", "<NA>": "", "NaT": "", "NaN": ""})
        )
    return out


def dataframe_from_bytes(raw: bytes, filename: str = "") -> Any:
    """Load a masterdata table from CSV or Parquet bytes."""
    import pandas as _pd
    from io import BytesIO, StringIO

    name = (filename or "").lower()
    is_parquet = name.endswith(".parquet") or (
        len(raw) >= 4 and raw[:4] == b"PAR1"
    )
    if is_parquet:
        try:
            df = _pd.read_parquet(BytesIO(raw))
        except Exception as exc:
            raise ValueError(f"Lecture Parquet impossible: {exc}") from exc
        return _dataframe_as_str(df)

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
    return _dataframe_as_str(df)


def read_masterdata_dataframe(path: Path) -> Any:
    """Load CSV or Parquet from disk into a string-normalized DataFrame."""
    import pandas as _pd

    suffix = path.suffix.lower()
    if suffix == ".parquet":
        df = _pd.read_parquet(path)
        return _dataframe_as_str(df)
    df = _pd.read_csv(
        str(path),
        sep=";",
        dtype=str,
        keep_default_na=False,
        on_bad_lines="skip",
        encoding="utf-8",
        encoding_errors="replace",
    )
    return _dataframe_as_str(df)


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
                        "warnings": ["Cache non chargé - rechargement recommandé."],
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
        log.warning("pandas not available - masterdata cache disabled")
        return {"error": "pandas not available"}

    with _MC_LOCK:
        for key, fname in MD_FILES.items():
            fpath = resolve_source_path(key)
            src_type = "workspace" if key in MD_LAST_SYNC else "bundled"
            if fpath.suffix.lower() == ".parquet" and key not in MD_LAST_SYNC:
                src_type = "parquet"
            prev_entry = CACHE.get(key)
            try:
                if not fpath.exists():
                    raise FileNotFoundError(fpath)
                df = read_masterdata_dataframe(fpath)
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
                    "fname": fpath.name,
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
                    "MD cache: %s - %d rows  schema_valid=%s  source=%s",
                    fpath.name, len(df), schema_info["schema_valid"], src_type,
                )
            except FileNotFoundError:
                if prev_entry and prev_entry.get("df") is not None:
                    fallback = dict(prev_entry)
                    fallback["source"] = "fallback"
                    fallback["warnings"] = list(prev_entry.get("warnings", [])) + [
                        f"Fichier introuvable: {fpath} - données précédentes conservées."
                    ]
                    CACHE[key] = fallback
                    MD_SOURCE[key] = "fallback"
                    log.warning("MD cache: %s MISSING - Tier C fallback active", fname)
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
                        f"Erreur rechargement: {exc} - données précédentes conservées."
                    ]
                    CACHE[key] = fallback
                    MD_SOURCE[key] = "fallback"
                    log.warning("MD cache: %s ERROR - Tier C fallback: %s", fname, exc)
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
    if df is not None and key == "materials":
        # Afficher / chercher toutes les colonnes présentes dans le fichier Materials.
        cols = [str(c) for c in df.columns]
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
            "channel": row_value(row, "VTWEG", "channel") or "-",
            "division": row_value(row, "SPART", "division") or "-",
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
        fields = {str(k): str(v) if v is not None else "" for k, v in row.items()}
        # Enrich Commentaire for replaced articles: date alone → full sentence.
        statut = row_value(row, "Statut", "statut", "status")
        commentaire = row_value(row, "Commentaire", "commentaire", "comment")
        replacement = _statut_as_replacement_matnr(statut)
        if replacement and replacement != normalize_article_code(matnr):
            enriched = format_material_replacement_commentaire(
                replacement=replacement,
                commentaire=commentaire,
                article=matnr,
            )
            for key in list(fields.keys()):
                if str(key).strip().lower() in {"commentaire", "comment", "comments", "bemerkung"}:
                    fields[key] = enriched
            if not any(str(k).strip().lower() == "commentaire" for k in fields):
                fields["Commentaire"] = enriched
        out.append({
            "id": matnr or f"mat-{i}",
            "materialId": matnr,
            "description": row_value(row, "MAKTX", "maktx", "description"),
            "updatedAt": sync_at,
            "fields": fields,
        })
    return out


def format_rules(search: str = "") -> list[dict]:
    from src.rejection_catalog import REJECTION_CATALOG, review_actions

    q = (search or "").strip().lower()
    out: list[dict] = []
    for code, entry in REJECTION_CATALOG.items():
        message = str(entry.get("message_fr") or "")
        severity = str(entry.get("severity") or "")
        actions = review_actions(code)
        haystack = " ".join([
            code,
            message,
            severity,
            actions["button_accept"],
            actions["button_reject"],
            actions["auto_action_accept"],
            actions["auto_action_reject"],
            actions["mode"],
        ]).lower()
        if q and q not in haystack:
            continue
        out.append({
            "id": code,
            "code": code,
            "severity": severity,
            "businessStatus": entry.get("business_status") or "",
            "message": message,
            "retryAllowed": bool(entry.get("retry_allowed")),
            "manualReview": bool(entry.get("manual_review_required")),
            "buttonAccept": actions["button_accept"],
            "buttonReject": actions["button_reject"],
            "autoActionAccept": actions["auto_action_accept"],
            "autoActionReject": actions["auto_action_reject"],
            "mode": actions["mode"],
            "fields": {
                "code": code,
                "severity": severity,
                "business_status": str(entry.get("business_status") or ""),
                "message_fr": message,
                "message_en": str(entry.get("message_en") or ""),
                "retry_allowed": str(bool(entry.get("retry_allowed"))),
                "manual_review_required": str(bool(entry.get("manual_review_required"))),
                "button_accept": actions["button_accept"],
                "button_reject": actions["button_reject"],
                "auto_action_accept": actions["auto_action_accept"],
                "auto_action_reject": actions["auto_action_reject"],
                "mode": actions["mode"],
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
        "salesorders": "salesorders",
        "salesorder": "salesorders",
        "commandes": "salesorders",
    }
    key = mapping.get((kind or "").strip().lower())
    if not key:
        raise ValueError(f"Type masterdata inconnu: {kind}")
    return key


_FILENAME_KIND_PREFIXES: tuple[tuple[str, str], ...] = (
    ("10564_customers", "customers"),
    ("10564_partners", "partners"),
    ("db_materials", "materials"),
    ("10564_materials", "materials"),
    ("db_salesorder", "salesorders"),
)


def kind_key_from_filename(filename: str) -> str | None:
    """Map Bosch masterdata filenames to internal cache keys."""
    base = (filename or "").strip().replace("\\", "/").rsplit("/", 1)[-1].lower()
    if not base.endswith((".csv", ".parquet")):
        return None
    stem = base.rsplit(".", 1)[0]
    for prefix, key in _FILENAME_KIND_PREFIXES:
        if stem == prefix:
            return key
    return None


def write_csv(key: str, df) -> None:
    fname = MD_FILES[key]
    path = runtime_dir() / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, sep=";", index=False, encoding="utf-8")
    tmp.replace(path)
    MD_LAST_SYNC[key] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    load_cache()


def import_dataframe(key: str, raw: bytes, filename: str = "") -> dict:
    df = dataframe_from_bytes(raw, filename=filename)
    schema = validate_schema(key, df)
    if not schema["schema_valid"]:
        missing = ", ".join(schema["missing_columns"])
        raise ValueError(f"Colonnes manquantes pour {key}: {missing}")
    if len(df) == 0:
        raise ValueError("Fichier masterdata vide")
    write_csv(key, df)
    name = (filename or "").lower()
    is_parquet = name.endswith(".parquet") or (len(raw) >= 4 and raw[:4] == b"PAR1")
    if is_parquet:
        pq_name = MD_PARQUET_FILES.get(key)
        if pq_name:
            pq_path = runtime_dir() / pq_name
            pq_path.parent.mkdir(parents=True, exist_ok=True)
            pq_path.write_bytes(raw)
    return {
        "kind": key,
        "rows": int(len(df)),
        "file": MD_PARQUET_FILES.get(key) if is_parquet else MD_FILES[key],
        "format": "parquet" if is_parquet else "csv",
    }


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
