from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.masterdata import get_master_data, validate_order_number
from app.text_utils import compact_text, norm_order_key, unique


ORDER_STOP_WORDS = (
    "page",
    " le ",
    " du ",
    " date",
    " tel",
    " fax",
    " total",
    " livraison",
    " facture",
    " plusieurs",
    " agence",
    " destinataire",
)


def clean_order_candidate(value: str) -> str:
    candidate = compact_text(value)
    candidate = re.split(r"\b(?:Page|Le|Du|Date|Tel|Fax|Total|Livraison|Facture)\b", candidate, maxsplit=1, flags=re.I)[0]
    candidate = candidate.strip(" :;,.#")
    return compact_text(candidate)


def order_shape(value: str) -> str:
    shape = []
    for char in value.upper():
        if char.isalpha():
            shape.append("A")
        elif char.isdigit():
            shape.append("9")
        elif char.isspace():
            shape.append(" ")
        else:
            shape.append(char)
    grouped = []
    for char in shape:
        if grouped and grouped[-1][0] == char:
            grouped[-1] = (char, grouped[-1][1] + 1)
        else:
            grouped.append((char, 1))
    return "".join(char + (str(count) if count > 1 else "") for char, count in grouped)


def plausible_order_candidate(value: str) -> bool:
    if value and value[0].islower():
        return False
    if re.fullmatch(r"\d+[,.]\d{2}", value):
        return False
    key = norm_order_key(value)
    if len(key) < 5 or len(key) > 24:
        return False
    if key in {"COMMANDE", "FOURNISSEUR", "CLIENT", "LIVRAISON"}:
        return False
    if not re.search(r"\d", key):
        return False
    return bool(re.fullmatch(r"[A-Z0-9][A-Z0-9_./ -]{3,}[A-Z0-9]", value, flags=re.I))


class CustomerOrderNumberEngine:
    """Extract customer purchase order numbers independently from masterdata validation."""

    ENGINE_NAME = "customer_order_number"

    def __init__(self) -> None:
        self._templates: set[str] | None = None

    def templates_from_masterdata(self, limit: int = 80) -> set[str]:
        if self._templates is not None:
            return self._templates
        data = get_master_data()
        counter: Counter[str] = Counter()
        for key in data.get("salesorders_by_bstnk", {}):
            if len(key) >= 5:
                counter[order_shape(key)] += 1
        self._templates = {shape for shape, _count in counter.most_common(limit)}
        return self._templates

    def extract_candidates(self, text: str, filename: str | None = None) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        compact = compact_text(text)
        patterns = [
            (r"(?:N[^\w\s]{0,3}\s*(?:de\s*)?commande|commande\s*N[^\w\s]{0,3}|commande|votre\s+commande|order\s+no)\s*:?\s*([A-Z0-9][A-Z0-9_./ -]{4,40})", 70, "label_commande"),
            (r"\b(CM-\d{5,}|[A-Z]{2,}-\d{5,}|CAC\d{4}[A-Z]{2,}\d{4,}|ST\s+\d+\s+CSP\s+\d+)\b", 55, "known_format"),
        ]
        label_line_pattern = re.compile(
            r"(?:N[^\w\s]{0,3}\s*(?:de\s*)?commande|commande\s*N[^\w\s]{0,3}|commande|votre\s+commande|order\s+no)\s*:?\s*([A-Z0-9][A-Z0-9_./ -]{4,40})",
            flags=re.I,
        )
        for line in text.splitlines():
            match = label_line_pattern.search(line)
            if match:
                raw = clean_order_candidate(match.group(1))
                if plausible_order_candidate(raw):
                    candidates.append({"value": raw, "score": 85, "source": "label_commande_line"})

        for pattern, base_score, source in patterns:
            for match in re.finditer(pattern, compact, flags=re.I):
                raw = clean_order_candidate(match.group(1))
                if plausible_order_candidate(raw):
                    candidates.append({"value": raw, "score": base_score, "source": source})

        for line_number, line in enumerate(text.splitlines()):
            if "commande" not in line.lower():
                continue
            for following in text.splitlines()[line_number + 1 : line_number + 3]:
                raw = clean_order_candidate(following.split("|", 1)[0])
                if plausible_order_candidate(raw):
                    candidates.append({"value": raw, "score": 45, "source": "line_after_label"})

        if filename:
            for raw in re.findall(r"(?<!\d)(\d{6,10})(?!\d)", filename):
                candidates.append({"value": raw, "score": 20, "source": "filename"})

        templates = self.templates_from_masterdata()
        normalized_seen = set()
        results = []
        data = get_master_data()
        for candidate in candidates:
            value = clean_order_candidate(candidate["value"])
            key = norm_order_key(value)
            if key in normalized_seen:
                continue
            normalized_seen.add(key)
            score = int(candidate["score"])
            reasons = [candidate["source"]]
            if order_shape(key) in templates:
                score += 15
                reasons.append("template_masterdata")
            validation = validate_order_number(data, value)
            if validation.get("Statut") == "Confirmee master data":
                score += 120
                reasons.append("confirmed_masterdata")
            elif validation.get("Statut") == "Non trouvee master data":
                reasons.append("not_found_masterdata")
            if any(stop in f" {value.lower()} " for stop in ORDER_STOP_WORDS):
                score -= 40
                reasons.append("contains_context_stop")
            # Penalize Bosch article codes (EL/ELM + 10+ digits)
            if re.fullmatch(r"EL[M]?\s?\d{10,}", value, flags=re.IGNORECASE):
                score -= 60
                reasons.append("bosch_article_code")
            # Penalize VAT numbers (FR + 2 key digits + 9 SIREN digits)
            if re.match(r"FR\s?\d{2}\s?\d{9}", value, flags=re.IGNORECASE):
                score -= 70
                reasons.append("vat_number")
            # Penalize phrases / sentences captured as order numbers
            if len(value.split()) >= 4:
                score -= 50
                reasons.append("too_many_words")
            # Penalize date patterns (dd/mm/yyyy, yyyy-mm-dd)
            if re.fullmatch(r"\d{2}/\d{2}/\d{4}", value) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                score -= 60
                reasons.append("date_pattern")
            results.append(
                {
                    "value": value,
                    "normalized": key,
                    "score": score,
                    "reasons": reasons,
                    "validation": validation,
                    "shape": order_shape(key),
                }
            )

        results.sort(key=lambda item: item["score"], reverse=True)
        return results

    def extract(self, text: str, filename: str | None = None) -> dict[str, Any]:
        candidates = self.extract_candidates(text, filename)
        best = candidates[0] if candidates else None
        return {
            "engine": self.ENGINE_NAME,
            "order_number": best["value"] if best else None,
            "status": best["validation"].get("Statut") if best else "Non detecte",
            "candidates": candidates[:8],
            "templates_count": len(self.templates_from_masterdata()),
        }
