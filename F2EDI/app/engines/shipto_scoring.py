"""SHIPTO Scoring Engine — Evidence-based candidate ranking.

Architecture:
  1. Generate all SHIPTO candidates for a SOLDTO
  2. Score each candidate against evidence found in the PDF
  3. Return ranked candidates with scores, reason_codes, explanation
  4. LLM fallback only if top score < 95 or gap with #2 < 15

Scoring grid (from recommendations doc):
  +40  Code postal SHIPTO present dans le PDF
  +30  Rue normalisee presente dans le PDF
  +35  Code agence detecte et lie au SHIPTO
  +20  Ville SHIPTO presente dans le PDF
  +20  Commande/historique deja associe au SHIPTO
  +10  Nom agence ou nom client proche
  -40  Code postal d'un autre SHIPTO mieux represente
  -50  Adresse clairement contradictoire
  -30  Absence totale de preuve adresse
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any


# ─── Normalization helpers ───────────────────────────────────────────────────

_ABBREVIATIONS = {
    "ST": "SAINT", "STE": "SAINTE", "AV": "AVENUE", "BD": "BOULEVARD",
    "PL": "PLACE", "RTE": "ROUTE", "IMP": "IMPASSE", "ALL": "ALLEE",
    "CHE": "CHEMIN", "CHEM": "CHEMIN", "SQ": "SQUARE",
}


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def normalize_text(s: str) -> str:
    """Normalize for comparison: uppercase, no accents, collapse whitespace,
    replace special quotes/dashes, expand abbreviations."""
    if not s:
        return ""
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = s.replace("\xa0", " ")
    s = _strip_accents(s).upper()
    s = re.sub(r"[^A-Z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Expand abbreviations
    tokens = s.split()
    expanded = [_ABBREVIATIONS.get(t, t) for t in tokens]
    return " ".join(expanded)


def normalize_postal(s: str) -> str:
    """Keep only digits from postal code."""
    return re.sub(r"[^0-9]", "", s or "")[:5]


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class ScoringEvidence:
    """All evidence extracted from the PDF text for scoring."""
    text_normalized: str = ""
    text_raw: str = ""
    # Extracted signals
    postal_codes_in_text: list[str] = field(default_factory=list)
    cities_in_text: list[str] = field(default_factory=list)
    streets_in_text: list[str] = field(default_factory=list)
    agency_codes: list[str] = field(default_factory=list)  # [slash_code, cac_code]
    order_numbers: list[str] = field(default_factory=list)
    delivery_section: str = ""  # Normalized text near delivery keywords
    billing_section: str = ""  # Normalized text near billing keywords (for contradiction detection)


@dataclass
class CandidateScore:
    """Scored SHIPTO candidate."""
    shipto_id: str = ""
    name: str = ""
    street: str = ""
    city: str = ""
    postal: str = ""
    country: str = "FR"
    score: int = 0
    reason_codes: list[str] = field(default_factory=list)
    evidence_details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoringResult:
    """Final result of SHIPTO scoring."""
    best_candidate: CandidateScore | None = None
    all_candidates: list[CandidateScore] = field(default_factory=list)
    decision: str = "REJECTED"  # ACCEPTED, REVIEW, REJECTED, ERROR
    shipto_confidence: int = 0
    soldto_confidence: int = 0
    reason_codes: list[str] = field(default_factory=list)
    matched_by: list[str] = field(default_factory=list)
    explanation: str = ""
    llm_used: bool = False
    error: str = ""


# ─── Evidence extraction ─────────────────────────────────────────────────────

_DELIVERY_KEYWORDS = [
    "LIVRAISON", "LIVRER", "SHIP TO", "ADRESSE DE LIVRAISON",
    "DESTINATAIRE", "LIEU DE LIVRAISON", "DELIVER TO",
    "ADRESSE LIVRAISON", "LIVREE A", "EXPEDIER A",
]


def extract_evidence(text: str) -> ScoringEvidence:
    """Extract all scoring evidence from the PDF text."""
    ev = ScoringEvidence()
    ev.text_raw = text
    ev.text_normalized = normalize_text(text)

    # Extract postal codes (French: 5 digits starting with 0-9)
    ev.postal_codes_in_text = list(set(re.findall(r"\b(\d{5})\b", text)))

    # Extract delivery section (text near delivery keywords, avoiding billing section)
    text_upper = text.upper()
    _BILLING_KEYWORDS = ["FACTURATION", "FACTURE A", "FACTUREE A", "BILL TO", "ADRESSE DE FACTURATION", "SIEGE"]
    
    for kw in _DELIVERY_KEYWORDS:
        idx = text_upper.find(kw)
        if idx >= 0:
            # Take 400 chars after the keyword
            section_raw = text[max(0, idx - 20):idx + 500]
            # But stop if we hit a billing keyword (means we crossed into billing section)
            section_upper = section_raw.upper()
            for bkw in _BILLING_KEYWORDS:
                bkw_pos = section_upper.find(bkw, len(kw) + 5)
                if bkw_pos > 0:
                    section_raw = section_raw[:bkw_pos]
                    break
            ev.delivery_section = normalize_text(section_raw)
            break
    
    # ALSO: extract billing section to detect contradictions
    billing_section = ""
    _BILLING_KW_LIST = ["FACTURATION", "FACTURE A", "FACTUREE A", "BILL TO", "ADRESSE DE FACTURATION"]
    for bkw in _BILLING_KW_LIST:
        bidx = text_upper.find(bkw)
        if bidx >= 0:
            billing_section = normalize_text(text[max(0, bidx - 20):bidx + 400])
            break
    ev.billing_section = billing_section

    # Extract agency codes from order number
    # Pattern 1: "N° de commande : CAC2401CFL00018 / NTE"
    for line in text.split("\n"):
        if "commande" in line.lower() and "/" in line:
            parts = line.split("/")
            if len(parts) >= 2:
                after_slash = parts[1].strip().split()[0] if parts[1].strip() else ""
                if after_slash.isalpha() and after_slash.isupper() and 2 <= len(after_slash) <= 5:
                    ev.agency_codes.append(after_slash)
            break

    # Pattern 2: CAC2408CHA00055 → extract "CHA"
    m = re.search(r"CAC\d{4}([A-Z]{2,4})\d+", text)
    if m:
        cac_code = m.group(1)
        if cac_code not in ev.agency_codes:
            ev.agency_codes.append(cac_code)

    # Extract order numbers
    # CAC numbers
    for m in re.finditer(r"(CAC\d{4}[A-Z]{2,5}\d+)", text):
        ev.order_numbers.append(m.group(1))
    # Standard PO numbers
    m = re.search(r"(?:PO|Commande)[\s:]*([\w\-]+)", text, re.IGNORECASE)
    if m:
        ev.order_numbers.append(m.group(1))

    return ev


# ─── Scoring engine ──────────────────────────────────────────────────────────

def score_candidate(
    candidate: dict,
    evidence: ScoringEvidence,
    soldto_postal: str,
    all_candidates_postals: set[str],
    order_history: list[dict] | None = None,
) -> CandidateScore:
    """Score a single SHIPTO candidate against extracted evidence."""
    cs = CandidateScore(
        shipto_id=candidate.get("id", ""),
        name=candidate.get("name", ""),
        street=candidate.get("street", ""),
        city=candidate.get("city", ""),
        postal=candidate.get("postal", ""),
        country=candidate.get("country", "FR"),
    )

    cand_postal = normalize_postal(cs.postal)
    cand_city_norm = normalize_text(cs.city)
    cand_street_norm = normalize_text(cs.street)
    soldto_postal_norm = normalize_postal(soldto_postal)

    has_any_address_proof = False

    # ── SCORE: Code postal present dans le PDF (+40) ──
    if cand_postal and cand_postal in evidence.postal_codes_in_text:
        # Extra check: is it in the delivery section specifically?
        if evidence.delivery_section and cand_postal in evidence.delivery_section:
            cs.score += 40
            cs.reason_codes.append("POSTAL_IN_DELIVERY_SECTION")
            has_any_address_proof = True
        elif not evidence.delivery_section:
            # No delivery section found, but postal is in text
            cs.score += 30
            cs.reason_codes.append("POSTAL_IN_TEXT")
            has_any_address_proof = True
        elif evidence.billing_section and cand_postal in evidence.billing_section:
            # Postal found ONLY in billing section, NOT delivery → likely HQ/billing address
            cs.score -= 20
            cs.reason_codes.append("POSTAL_IN_BILLING_ONLY")
        else:
            # Postal in text but NOT in delivery section
            cs.score += 15
            cs.reason_codes.append("POSTAL_IN_TEXT_NOT_DELIVERY")
    elif cand_postal and cand_postal == soldto_postal_norm:
        # Postal matches SOLDTO headquarters — no extra evidence
        pass

    # ── SCORE: Rue normalisee dans le PDF (+30) ──
    if cand_street_norm and len(cand_street_norm) > 5:
        if cand_street_norm in evidence.text_normalized:
            cs.score += 30
            cs.reason_codes.append("STREET_IN_TEXT")
            has_any_address_proof = True
            # Bonus if also in delivery section
            if evidence.delivery_section and cand_street_norm in evidence.delivery_section:
                cs.score += 5
                cs.reason_codes.append("STREET_IN_DELIVERY_SECTION")

    # ── SCORE: Code agence detecte et lie au SHIPTO (+35) ──
    if evidence.agency_codes:
        cand_name_upper = (cs.name or "").upper()
        for code in evidence.agency_codes:
            # Check if agency code appears in candidate name (e.g. ".ISERBA (STQ)")
            if f"({code})" in cand_name_upper:
                cs.score += 35
                cs.reason_codes.append(f"AGENCY_CODE_MATCH:{code}")
                cs.evidence_details["agency_code"] = code
                has_any_address_proof = True
                break

    # ── SCORE: Ville SHIPTO dans le PDF (+20) ──
    if cand_city_norm and len(cand_city_norm) > 3:
        if cand_city_norm in evidence.text_normalized:
            cs.score += 20
            cs.reason_codes.append("CITY_IN_TEXT")
            has_any_address_proof = True
            # Bonus if in delivery section
            if evidence.delivery_section and cand_city_norm in evidence.delivery_section:
                cs.score += 5
                cs.reason_codes.append("CITY_IN_DELIVERY_SECTION")

    # ── SCORE: Historique commande (+20) ──
    if order_history:
        for hist in order_history:
            if hist.get("shipto") == cs.shipto_id:
                cs.score += 20
                cs.reason_codes.append("ORDER_HISTORY_MATCH")
                break

    # ── SCORE: Nom client proche (+10) ──
    if cs.name:
        name_norm = normalize_text(cs.name)
        # Remove leading dots and parenthetical codes
        name_clean = re.sub(r"\([A-Z]{2,5}\)", "", name_norm).strip()
        if name_clean and len(name_clean) > 4 and name_clean in evidence.text_normalized:
            cs.score += 10
            cs.reason_codes.append("NAME_IN_TEXT")

    # ── MALUS: Code postal d'un autre SHIPTO mieux represente (-40) ──
    if cand_postal:
        other_postals_in_delivery = [
            p for p in evidence.postal_codes_in_text
            if p != cand_postal and p != soldto_postal_norm and p in all_candidates_postals
        ]
        if other_postals_in_delivery and evidence.delivery_section:
            for op in other_postals_in_delivery:
                if op in evidence.delivery_section:
                    cs.score -= 40
                    cs.reason_codes.append(f"OTHER_POSTAL_IN_DELIVERY:{op}")
                    break

    # ── MALUS: Absence totale de preuve adresse (-30) ──
    if not has_any_address_proof:
        cs.score -= 30
        cs.reason_codes.append("NO_ADDRESS_EVIDENCE")

    return cs


# ─── Main scoring function ───────────────────────────────────────────────────

def score_shipto_candidates(
    text: str,
    soldto_id: str,
    masterdata: dict,
    soldto_confidence: int = 90,
) -> ScoringResult:
    """Score all SHIPTO candidates for a SOLDTO and return the best match.

    Args:
        text: Full extracted PDF text
        soldto_id: Identified SOLDTO
        masterdata: Loaded masterdata dict with indexes
        soldto_confidence: Confidence in SOLDTO identification

    Returns:
        ScoringResult with ranked candidates, decision, and reason_codes
    """
    result = ScoringResult(soldto_confidence=soldto_confidence)

    # 1. Get all candidates
    candidates = masterdata.get("partners_by_soldto", {}).get(soldto_id, [])
    if not candidates:
        result.error = f"No SHIPTO partners found for SOLDTO {soldto_id}"
        result.decision = "ERROR"
        result.reason_codes.append("NO_PARTNERS_FOR_SOLDTO")
        return result

    # If only 1 candidate, it's straightforward
    if len(candidates) == 1:
        single = candidates[0]
        result.best_candidate = CandidateScore(
            shipto_id=single["id"], name=single.get("name", ""),
            street=single.get("street", ""), city=single.get("city", ""),
            postal=single.get("postal", ""), country=single.get("country", "FR"),
            score=80, reason_codes=["SINGLE_SHIPTO_FOR_SOLDTO"],
        )
        result.shipto_confidence = 80
        result.decision = "REVIEW"
        result.reason_codes = ["SINGLE_SHIPTO_FOR_SOLDTO"]
        result.matched_by = ["soldto_unique_shipto"]
        result.all_candidates = [result.best_candidate]
        return result

    # 2. Extract evidence from text
    evidence = extract_evidence(text)

    # 3. Get SOLDTO postal for comparison
    soldto_info = masterdata.get("customers_by_id", {}).get(soldto_id)
    soldto_postal = soldto_info.get("postal", "") if soldto_info else ""

    # Collect all candidate postals for contradiction detection
    all_candidates_postals = set(normalize_postal(c.get("postal", "")) for c in candidates)

    # Get order history for this SOLDTO
    order_history = masterdata.get("salesorders_by_kunnr", {}).get(soldto_id, [])

    # 4. Score each candidate (SOLDTO excluded — it's the HQ, not a delivery point)
    scored: list[CandidateScore] = []
    for cand in candidates:
        if cand.get("id") == soldto_id:
            # SOLDTO itself should never win as delivery address
            # unless it's the ONLY candidate (handled above)
            continue
        cs = score_candidate(
            cand, evidence, soldto_postal, all_candidates_postals, order_history
        )
        scored.append(cs)

    # 5. Sort by score descending
    scored.sort(key=lambda x: x.score, reverse=True)
    result.all_candidates = scored

    if not scored:
        result.error = "No candidates scored"
        result.decision = "ERROR"
        return result

    best = scored[0]
    second_score = scored[1].score if len(scored) > 1 else -999
    gap = best.score - second_score

    # 6. Decision based on score and gap
    if best.score >= 95 and gap >= 15:
        # Strong unambiguous match
        result.decision = "ACCEPTED"
        result.shipto_confidence = 100
    elif best.score >= 85 and gap >= 15:
        # Good match but not fully proven
        result.decision = "REVIEW"
        result.shipto_confidence = best.score
    elif best.score >= 70:
        # Plausible but ambiguous — needs LLM
        result.decision = "REVIEW"
        result.shipto_confidence = best.score
        result.reason_codes.append("LLM_RECOMMENDED")
    elif best.score >= 40:
        result.decision = "REJECTED"
        result.shipto_confidence = best.score
        result.reason_codes.append("INSUFFICIENT_EVIDENCE")
    else:
        result.decision = "REJECTED"
        result.shipto_confidence = max(0, best.score)
        result.reason_codes.append("CRITICAL_NO_MATCH")

    # Check if gap is too small (ambiguity)
    if gap < 15 and best.score >= 40 and len(scored) > 1:
        result.reason_codes.append(f"AMBIGUOUS_GAP:{gap}")
        if result.decision == "ACCEPTED":
            result.decision = "REVIEW"
            result.reason_codes.append("DOWNGRADED_AMBIGUOUS")

    result.best_candidate = best
    result.matched_by = [rc for rc in best.reason_codes if not rc.startswith("NO_") and not rc.startswith("OTHER_")]
    result.reason_codes.extend(best.reason_codes)
    result.explanation = _build_explanation(best, second_score, gap, result.decision)

    return result


def _build_explanation(best: CandidateScore, second_score: int, gap: int, decision: str) -> str:
    """Build human-readable explanation."""
    parts = []
    parts.append(f"Best: {best.shipto_id} ({best.name}) score={best.score}")
    if second_score > -999:
        parts.append(f"gap with #2={gap}")
    evidence_str = ", ".join(best.reason_codes[:4])
    parts.append(f"evidence=[{evidence_str}]")
    parts.append(f"decision={decision}")
    return " | ".join(parts)


# ─── LLM fallback (encadre) ──────────────────────────────────────────────────

def llm_arbitrate_top_candidates(
    text: str,
    top_candidates: list[CandidateScore],
    evidence: ScoringEvidence,
) -> dict | None:
    """Ask LLM to arbitrate between top 2-3 candidates.

    Only called when:
    - Best score < 95, OR
    - Gap between #1 and #2 < 15

    Returns: {"chosen_id": str, "confidence": int, "justification": str} or None
    """
    try:
        from app.engines.llm_resolver import _call_llm
        import json

        # Build prompt with only top 3 candidates
        candidates_desc = []
        for i, c in enumerate(top_candidates[:3], 1):
            candidates_desc.append(
                f"  Candidat {i}: SHIPTO={c.shipto_id}, Nom={c.name}, "
                f"Adresse={c.street}, {c.postal} {c.city}, "
                f"Score={c.score}, Preuves={c.reason_codes}"
            )

        # Inject memo context for edge cases
        memo_context = ""
        try:
            from app.memo import build_memo_context_for_llm
            # Get client name from first candidate
            _client = top_candidates[0].name if top_candidates else ""
            memo_context = build_memo_context_for_llm(text, client_name=_client)
        except Exception:
            pass

        prompt = f"""Tu es un expert en logistique. Tu dois determiner l'adresse de LIVRAISON correcte.
{memo_context}

EXTRAIT DU DOCUMENT (section pertinente):
{text[:2500]}

CANDIDATS SHIPTO (scores par preuves documentaires):
{chr(10).join(candidates_desc)}

CODES AGENCE DETECTES DANS LE PDF: {evidence.agency_codes or 'aucun'}
CODES POSTAUX DANS LE PDF: {evidence.postal_codes_in_text[:5]}

QUESTION: Quel candidat correspond a l'adresse de LIVRAISON du document?
Si tu ne peux pas determiner avec certitude, reponds "INCERTAIN".

Reponds en JSON strict:
{{"choix": 1 ou 2 ou 3, "confiance": 0-100, "justification": "explication courte"}}
Ou si incertain:
{{"choix": 0, "confiance": 0, "justification": "raison"}}"""

        response = _call_llm(prompt, max_tokens=200)

        # Parse JSON from response
        json_match = re.search(r"\{[^}]+\}", response)
        if json_match:
            data = json.loads(json_match.group())
            choix = int(data.get("choix", 0))
            if 1 <= choix <= len(top_candidates):
                chosen = top_candidates[choix - 1]
                return {
                    "chosen_id": chosen.shipto_id,
                    "confidence": int(data.get("confiance", 0)),
                    "justification": data.get("justification", ""),
                }
        return None
    except Exception:
        return None


# ─── Full pipeline: score + LLM fallback ─────────────────────────────────────

def resolve_shipto_with_scoring(
    text: str,
    soldto_id: str,
    masterdata: dict,
    soldto_confidence: int = 90,
    use_llm_fallback: bool = True,
) -> ScoringResult:
    """Complete SHIPTO resolution: scoring + optional LLM fallback.

    This is the main entry point for the scoring engine.
    """
    # Run initial scoring
    result = score_shipto_candidates(text, soldto_id, masterdata, soldto_confidence)

    if result.decision == "ERROR" or not result.best_candidate:
        return result

    # Check if LLM arbitration is needed
    best = result.best_candidate
    second_score = result.all_candidates[1].score if len(result.all_candidates) > 1 else -999
    gap = best.score - second_score

    needs_llm = (
        use_llm_fallback
        and len(result.all_candidates) > 1
        and (best.score < 95 or gap < 15)
        and best.score >= 30  # Don't waste LLM on hopeless cases
    )

    if needs_llm:
        evidence = extract_evidence(text)
        llm_result = llm_arbitrate_top_candidates(
            text, result.all_candidates[:3], evidence
        )

        if llm_result and llm_result["chosen_id"]:
            result.llm_used = True
            chosen_id = llm_result["chosen_id"]

            # Find the chosen candidate
            for c in result.all_candidates:
                if c.shipto_id == chosen_id:
                    result.best_candidate = c
                    break

            llm_conf = llm_result["confidence"]
            result.reason_codes.append(f"LLM_CONFIRMED:{chosen_id}")
            result.explanation += f" | LLM: {llm_result['justification']}"

            # Adjust decision based on LLM confidence
            if llm_conf >= 80 and result.best_candidate.score >= 70:
                result.decision = "REVIEW"  # Good but LLM-assisted
                result.shipto_confidence = min(90, result.best_candidate.score + 15)
            elif llm_conf >= 60:
                result.decision = "REVIEW"
                result.shipto_confidence = min(85, result.best_candidate.score + 10)
            else:
                result.decision = "REJECTED"
                result.shipto_confidence = max(30, llm_conf)
                result.reason_codes.append("LLM_LOW_CONFIDENCE")

        elif llm_result is None and best.score < 70:
            # LLM failed and score is low — reject
            result.decision = "REJECTED"
            result.reason_codes.append("LLM_FAILED")

    # Final post-validation: ensure no contradiction
    result = _post_validate(result, text)

    return result


def _post_validate(result: ScoringResult, text: str) -> ScoringResult:
    """Post-validation: block ACCEPTED if postal code not in document."""
    if not result.best_candidate:
        return result

    best = result.best_candidate
    cand_postal = normalize_postal(best.postal)

    if not cand_postal:
        return result

    # Check: is the postal code of the best candidate in the PDF text?
    if cand_postal not in text:
        # CRITICAL: postal of selected SHIPTO is NOT in the document
        if result.decision == "ACCEPTED":
            result.decision = "REVIEW"
            result.reason_codes.append("POST_VALIDATION_POSTAL_MISSING")
            result.shipto_confidence = min(result.shipto_confidence, 85)

        # Check if a DIFFERENT postal is in the delivery section
        evidence = extract_evidence(text)
        if evidence.delivery_section:
            other_postals = [
                p for p in evidence.postal_codes_in_text
                if p != cand_postal
            ]
            for op in other_postals:
                if op in evidence.delivery_section:
                    # There IS a postal in the delivery section, and it's not our candidate's!
                    result.decision = "REJECTED"
                    result.shipto_confidence = 0
                    result.reason_codes.append(f"CONTRADICTORY_POSTAL_IN_DELIVERY:{op}")
                    result.error = f"Postal {cand_postal} du SHIPTO non trouve, mais {op} present dans section livraison"
                    break

    return result
