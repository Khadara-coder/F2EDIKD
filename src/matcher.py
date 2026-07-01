"""Sold-to and Ship-to matching engine.

Matching policy derived from n8n regression tests:
- Postal exact match is primary evidence
- City exact match is primary evidence  
- Street match is a tie-breaker ONLY (street-only must never qualify)
- Strong evidence requires postal exact OR city exact
- VAT normalization applied before any comparison
- Minimum confidence: Sold-to=75, Ship-to=80
- Ship-to candidates are pre-filtered by detected Sold-to
- Unique score gap >= 15 required to auto-select when postal/city absent
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from .exceptions import MatchingError

log = logging.getLogger("edifact.matcher")

_SOLDTO_MIN_CONFIDENCE = 75
_SHIPTO_MIN_CONFIDENCE = 80
_UNIQUE_GAP_REQUIRED = 15


# --------------------------------------------------------------------------- #
# Text normalisation helpers
# --------------------------------------------------------------------------- #

def _normalize_text(s: str) -> str:
    """Lowercase, strip accents, compress whitespace."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _normalize_postal(s: str) -> str:
    """Strip non-digit, non-letter chars from postal code."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _normalize_vat(s: str) -> str:
    """Normalize VAT number: remove spaces, punctuation, lowercase.

    Derived from n8n regression-vat-normalization.js.
    """
    s = re.sub(r"[\s.\-]", "", (s or "").upper())
    return s


def _token_overlap(a: str, b: str) -> float:
    """Return token-based Jaccard overlap score [0..100]."""
    tokens_a = set(_normalize_text(a).split())
    tokens_b = set(_normalize_text(b).split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return 100.0 * len(intersection) / len(union)


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #

@dataclass
class ScoredCandidate:
    """A matching candidate with its evidence scores."""
    row: dict[str, str]
    score: float = 0.0
    evidence: list[str] = field(default_factory=list)
    has_postal_match: bool = False
    has_city_match: bool = False
    has_street_only: bool = False


def _score_candidate(
    candidate: dict[str, str],
    name_query: str,
    street_query: str,
    postal_query: str,
    city_query: str,
    vat_query: str,
) -> ScoredCandidate:
    """Score a single master-data row against query evidence."""
    sc = ScoredCandidate(row=candidate)
    score = 0.0

    norm_postal_q = _normalize_postal(postal_query)
    norm_postal_c = _normalize_postal(candidate.get("postal_code", ""))
    norm_city_q = _normalize_text(city_query)
    norm_city_c = _normalize_text(candidate.get("city", ""))
    norm_street_q = _normalize_text(street_query)
    norm_street_c = _normalize_text(candidate.get("street", ""))
    norm_name_q = _normalize_text(name_query)
    norm_name_c = _normalize_text(candidate.get("name", ""))
    norm_vat_q = _normalize_vat(vat_query)
    norm_vat_c = _normalize_vat(candidate.get("vat", ""))

    # VAT exact: decisive signal - raises score above Sold-to threshold alone
    if norm_vat_q and norm_vat_c and norm_vat_q == norm_vat_c:
        score += 80
        sc.has_postal_match = True  # VAT treated as strong evidence
        sc.evidence.append("VAT_EXACT")

    # Postal exact
    if norm_postal_q and norm_postal_c and norm_postal_q == norm_postal_c:
        score += 35
        sc.has_postal_match = True
        sc.evidence.append("POSTAL_EXACT")
    elif norm_postal_q and norm_postal_c and norm_postal_c.startswith(norm_postal_q[:3]):
        score += 15
        sc.evidence.append("POSTAL_PREFIX")

    # City exact / partial
    if norm_city_q and norm_city_c and norm_city_q == norm_city_c:
        score += 30
        sc.has_city_match = True
        sc.evidence.append("CITY_EXACT")
    elif norm_city_q and norm_city_c:
        city_sim = _token_overlap(norm_city_q, norm_city_c)
        if city_sim >= 60:
            score += city_sim * 0.2
            sc.evidence.append(f"CITY_PARTIAL({city_sim:.0f})")

    # Street (tie-breaker only)
    if norm_street_q and norm_street_c:
        street_sim = _token_overlap(norm_street_q, norm_street_c)
        if street_sim >= 50:
            score += street_sim * 0.1
            sc.evidence.append(f"STREET({street_sim:.0f})")
            if not sc.has_postal_match and not sc.has_city_match:
                sc.has_street_only = True

    # Name overlap
    if norm_name_q and norm_name_c:
        name_sim = _token_overlap(norm_name_q, norm_name_c)
        score += name_sim * 0.15
        sc.evidence.append(f"NAME({name_sim:.0f})")

    # Combined postal+city bonus when both primary signals are present
    if sc.has_postal_match and sc.has_city_match:
        score += 15
        sc.evidence.append("POSTAL_CITY_COMBINED")

    sc.score = round(score, 2)
    return sc


# --------------------------------------------------------------------------- #
# Public matching API
# --------------------------------------------------------------------------- #

def match_soldto(
    customers: list[dict[str, str]],
    name_query: str,
    street_query: str = "",
    postal_query: str = "",
    city_query: str = "",
    vat_query: str = "",
) -> dict[str, str]:
    """Match a PDF buyer to a Sold-to in the customer master.

    Args:
        customers: List of customer rows from master data.
        name_query: Buyer name extracted from PDF.
        street_query: Buyer street address.
        postal_query: Buyer postal code.
        city_query: Buyer city.
        vat_query: Buyer VAT number.

    Returns:
        Best-matching customer row dict.

    Raises:
        MatchingError: If no confident match is found or result is ambiguous.
    """
    scored = [
        _score_candidate(c, name_query, street_query, postal_query, city_query, vat_query)
        for c in customers
    ]
    scored.sort(key=lambda s: s.score, reverse=True)

    if not scored or scored[0].score < _SOLDTO_MIN_CONFIDENCE:
        top = scored[:3] if scored else []
        raise MatchingError(
            f"SOLDTO_LOW_CONFIDENCE: Best score {scored[0].score if scored else 0:.1f} "
            f"< threshold {_SOLDTO_MIN_CONFIDENCE}. "
            f"Query: name={name_query!r} postal={postal_query!r} city={city_query!r}. "
            f"Top candidates: {[(s.row.get('soldto'), s.score) for s in top]}"
        )

    best = scored[0]
    # Check for ambiguous top candidates
    if len(scored) >= 2:
        gap = best.score - scored[1].score
        if gap < _UNIQUE_GAP_REQUIRED and not best.has_postal_match and not best.has_city_match:
            raise MatchingError(
                f"SOLDTO_AMBIGUOUS: Score gap {gap:.1f} < {_UNIQUE_GAP_REQUIRED} "
                f"without strong postal/city evidence. "
                f"Top 2: {best.row.get('soldto')} ({best.score:.1f}), "
                f"{scored[1].row.get('soldto')} ({scored[1].score:.1f})"
            )

    log.info(
        "Sold-to matched: SOLDTO=%s score=%.1f evidence=%s",
        best.row.get("soldto"), best.score, best.evidence,
    )
    return best.row


def match_shipto(
    partners: list[dict[str, str]],
    soldto: str,
    name_query: str = "",
    street_query: str = "",
    postal_query: str = "",
    city_query: str = "",
) -> dict[str, str]:
    """Match a PDF delivery address to a Ship-to for a given Sold-to.

    Args:
        partners: All partner rows from master data.
        soldto: The resolved Sold-to number (filters partner candidates).
        name_query: Delivery name extracted from PDF.
        street_query: Delivery street.
        postal_query: Delivery postal code.
        city_query: Delivery city.

    Returns:
        Best-matching partner row dict.

    Raises:
        MatchingError: If Ship-to cannot be matched or evidence is too weak.
    """
    # Filter partners to only those belonging to this Sold-to
    candidates = [p for p in partners if p.get("soldto") == soldto]
    if not candidates:
        raise MatchingError(
            f"SHIPTO_NO_CANDIDATES: No partners found for Sold-to {soldto!r}"
        )

    scored = [
        _score_candidate(p, name_query, street_query, postal_query, city_query, "")
        for p in candidates
    ]
    scored.sort(key=lambda s: s.score, reverse=True)

    best = scored[0]

    # Street-only evidence is a blocking error per n8n policy
    if best.has_street_only and not best.has_postal_match and not best.has_city_match:
        raise MatchingError(
            f"SHIPTO_WEAK_EVIDENCE: Street-only match is not sufficient. "
            f"SHIPTO={best.row.get('shipto')} score={best.score:.1f}. "
            f"Require postal or city evidence."
        )

    if best.score < _SHIPTO_MIN_CONFIDENCE:
        raise MatchingError(
            f"SHIPTO_LOW_CONFIDENCE: Best score {best.score:.1f} "
            f"< threshold {_SHIPTO_MIN_CONFIDENCE}. "
            f"Sold-to={soldto} postal={postal_query!r} city={city_query!r}."
        )

    # Ambiguity check
    if len(scored) >= 2:
        gap = best.score - scored[1].score
        if gap < _UNIQUE_GAP_REQUIRED and not best.has_postal_match and not best.has_city_match:
            raise MatchingError(
                f"SHIPTO_AMBIGUOUS: Score gap {gap:.1f} < {_UNIQUE_GAP_REQUIRED}. "
                f"Top 2: {best.row.get('shipto')} ({best.score:.1f}), "
                f"{scored[1].row.get('shipto')} ({scored[1].score:.1f})"
            )

    log.info(
        "Ship-to matched: SHIPTO=%s SOLDTO=%s score=%.1f evidence=%s",
        best.row.get("shipto"), soldto, best.score, best.evidence,
    )
    return best.row


def derive_dept(postal_code: str) -> str:
    """Derive French department code from postal code.

    Rule from n8n FINAL_IMPLEMENTATION_STATUS: postal digits[0:2], fallback 'NA'.
    """
    digits = re.sub(r"[^0-9]", "", postal_code or "")
    return digits[:2] if len(digits) >= 2 else "NA"


def route_material_team(material_codes: list[str]) -> str:
    """Determine ADV routing team based on material-code composition.

    Rule from n8n FINAL_IMPLEMENTATION_STATUS:
    - TEAM 1: all codes start with '7' and none start with '8'
    - TEAM 2: mixed or any code starts with '8'
    """
    if not material_codes:
        return "TEAM 2"
    all_7 = all(str(code).startswith("7") for code in material_codes)
    has_8 = any(str(code).startswith("8") for code in material_codes)
    return "TEAM 1" if all_7 and not has_8 else "TEAM 2"
