"""POMPAC article resolution and anomaly logic.

Material resolution priority:
1. EAN lookup (lookup_ean_to_material.csv)
2. Fourre-tout lookup (lookup_fourretout_to_material.csv)
3. Direct material match against 10564_Materials.csv
4. Strict fuzzy description match
5. Reject if unresolved

Blocking checks after resolution:
- Discontinued materials (lookup_discontinued.csv)
- ROH / non-commercializable materials (lookup_roh_noncommercial.csv)
"""
from __future__ import annotations

import csv
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .exceptions import MaterialResolutionError

log = logging.getLogger("edifact.pompac")

_FUZZY_MIN_SCORE = 65.0  # Minimum token-overlap for description match


# --------------------------------------------------------------------------- #
# Lookup loading
# --------------------------------------------------------------------------- #

def _load_csv_lookup(
    path: str,
    key_col: str,
    value_col: str,
) -> dict[str, str]:
    """Load a simple key->value CSV lookup table.

    Lines starting with '#' are treated as comments and skipped.
    """
    p = Path(path)
    if not p.exists():
        log.warning("Lookup file not found (skipping): %s", path)
        return {}
    result: dict[str, str] = {}
    try:
        with open(p, newline="", encoding="utf-8-sig") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
            fh.seek(0)
            reader = csv.DictReader(
                (l for l in fh if not l.strip().startswith("#")),
            )
            for row in reader:
                k = (row.get(key_col) or "").strip()
                v = (row.get(value_col) or "").strip()
                if k and v:
                    result[k.upper()] = v
    except Exception as exc:
        log.warning("Error loading lookup %s: %s", path, exc)
    log.info("Lookup loaded: %s -> %d entries", Path(path).name, len(result))
    return result


def _load_set_lookup(path: str, key_col: str) -> frozenset[str]:
    """Load a CSV file as a frozenset of normalised keys."""
    p = Path(path)
    if not p.exists():
        log.warning("Set lookup not found (skipping): %s", path)
        return frozenset()
    result: set[str] = set()
    try:
        with open(p, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(
                (l for l in fh if not l.strip().startswith("#")),
            )
            for row in reader:
                k = (row.get(key_col) or "").strip().upper()
                if k:
                    result.add(k)
    except Exception as exc:
        log.warning("Error loading set lookup %s: %s", path, exc)
    log.info("Set lookup loaded: %s -> %d entries", Path(path).name, len(result))
    return frozenset(result)


@dataclass
class LookupTables:
    """All lookup tables used during material resolution."""
    ean_to_matnr: dict[str, str]          # EAN -> MATNR
    fourretout_to_matnr: dict[str, str]   # customer_code -> MATNR
    discontinued: frozenset[str]          # blocked MATNRs
    roh_noncommercial: frozenset[str]     # blocked MATNRs


def load_lookup_tables(
    ean_csv: str = "lookups/lookup_ean_to_material.csv",
    fourretout_csv: str = "lookups/lookup_fourretout_to_material.csv",
    discontinued_csv: str = "lookups/lookup_discontinued.csv",
    roh_csv: str = "lookups/lookup_roh_noncommercial.csv",
) -> LookupTables:
    """Load all lookup tables from disk."""
    return LookupTables(
        ean_to_matnr=_load_csv_lookup(ean_csv, "ean", "matnr"),
        fourretout_to_matnr=_load_csv_lookup(fourretout_csv, "customer_code", "matnr"),
        discontinued=_load_set_lookup(discontinued_csv, "matnr"),
        roh_noncommercial=_load_set_lookup(roh_csv, "matnr"),
    )


# --------------------------------------------------------------------------- #
# Normalisation / fuzzy helpers
# --------------------------------------------------------------------------- #

def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _token_overlap(a: str, b: str) -> float:
    ta = set(_normalize(a).split())
    tb = set(_normalize(b).split())
    if not ta or not tb:
        return 0.0
    return 100.0 * len(ta & tb) / len(ta | tb)


def _is_ean13(s: str) -> bool:
    return bool(re.match(r"^\d{12,13}$", (s or "").strip()))


# --------------------------------------------------------------------------- #
# Resolution result
# --------------------------------------------------------------------------- #

@dataclass
class ResolvedMaterial:
    """Result of a material resolution attempt."""
    matnr: str
    description: str
    resolution_method: str  # EAN / FOURRETOUT / DIRECT / FUZZY
    original_article: str
    confidence: float = 100.0


# --------------------------------------------------------------------------- #
# Main resolution function
# --------------------------------------------------------------------------- #

def resolve_material(
    article_code: str,
    description: str,
    ean_code: str,
    materials_master: dict[str, str],
    lookups: LookupTables,
) -> ResolvedMaterial:
    """Resolve a PDF article to a SAP MATNR using the POMPAC priority chain.

    Resolution order:
    1. EAN lookup
    2. Fourre-tout lookup
    3. Direct MATNR match
    4. Fuzzy description match
    5. Raise MaterialResolutionError(UNKNOWN_MATERIAL)

    Then blocking checks:
    - DISCONTINUED_MATERIAL
    - ROH_NONCOMMERCIAL

    Args:
        article_code: Customer article code from PDF.
        description: Article description from PDF.
        ean_code: EAN barcode from PDF (if any).
        materials_master: Dict[matnr -> description] from 10564_Materials.csv.
        lookups: Loaded LookupTables.

    Returns:
        ResolvedMaterial on success.

    Raises:
        MaterialResolutionError: On any resolution failure.
    """
    art_norm = (article_code or "").strip().upper()
    ean_norm = (ean_code or "").strip()

    # --- 1. EAN lookup ---
    if _is_ean13(ean_norm):
        matnr = lookups.ean_to_matnr.get(ean_norm)
        if matnr:
            return _checked(
                ResolvedMaterial(
                    matnr=matnr,
                    description=materials_master.get(matnr, description),
                    resolution_method="EAN",
                    original_article=article_code,
                ),
                lookups,
            )
        log.debug("EAN %s not in lookup table.", ean_norm)

    # --- 2. Fourre-tout lookup ---
    if art_norm:
        matnr = lookups.fourretout_to_matnr.get(art_norm)
        if matnr:
            return _checked(
                ResolvedMaterial(
                    matnr=matnr,
                    description=materials_master.get(matnr, description),
                    resolution_method="FOURRETOUT",
                    original_article=article_code,
                ),
                lookups,
            )

    # --- 3. Direct MATNR match ---
    if art_norm and art_norm in {k.upper() for k in materials_master}:
        matched_matnr = next(
            k for k in materials_master if k.upper() == art_norm
        )
        return _checked(
            ResolvedMaterial(
                matnr=matched_matnr,
                description=materials_master[matched_matnr],
                resolution_method="DIRECT",
                original_article=article_code,
            ),
            lookups,
        )

    # --- 4. Fuzzy description match ---
    if description:
        best_matnr: Optional[str] = None
        best_score = 0.0
        for matnr_candidate, desc_candidate in materials_master.items():
            score = _token_overlap(description, desc_candidate)
            if score > best_score:
                best_score = score
                best_matnr = matnr_candidate

        if best_score >= _FUZZY_MIN_SCORE and best_matnr:
            log.info(
                "Material fuzzy matched: article=%r description=%r -> matnr=%s score=%.1f",
                article_code, description, best_matnr, best_score,
            )
            return _checked(
                ResolvedMaterial(
                    matnr=best_matnr,
                    description=materials_master[best_matnr],
                    resolution_method="FUZZY",
                    original_article=article_code,
                    confidence=best_score,
                ),
                lookups,
            )
        log.debug(
            "Fuzzy description match failed: best score %.1f < %.1f for article=%r",
            best_score, _FUZZY_MIN_SCORE, article_code,
        )

    raise MaterialResolutionError(
        f"UNKNOWN_MATERIAL: Cannot resolve article={article_code!r} "
        f"ean={ean_code!r} description={description!r}"
    )


def _checked(result: ResolvedMaterial, lookups: LookupTables) -> ResolvedMaterial:
    """Apply blocking checks after initial resolution."""
    matnr_upper = result.matnr.upper()
    if matnr_upper in lookups.discontinued:
        raise MaterialResolutionError(
            f"DISCONTINUED_MATERIAL: MATNR {result.matnr!r} is discontinued."
        )
    if matnr_upper in lookups.roh_noncommercial:
        raise MaterialResolutionError(
            f"ROH_NONCOMMERCIAL: MATNR {result.matnr!r} is ROH/non-commercializable."
        )
    log.info(
        "Material resolved: matnr=%s method=%s confidence=%.1f",
        result.matnr, result.resolution_method, result.confidence,
    )
    return result
