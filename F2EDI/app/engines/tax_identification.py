from __future__ import annotations

import re
from typing import Any

from app.text_utils import compact_text, norm_key, unique


def only_digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def normalize_french_vat(value: str | None) -> str:
    key = norm_key(value or "")
    if not key.startswith("FR"):
        return key
    return key[:2] + re.sub(r"[^A-Z0-9]", "", key[2:])


def french_vat_from_siren(siren: str) -> str | None:
    digits = only_digits(siren)
    if len(digits) != 9:
        return None
    key = (12 + 3 * (int(digits) % 97)) % 97
    return f"FR{key:02d}{digits}"


def is_luhn_valid(value: str | None) -> bool:
    digits = only_digits(value)
    if not digits:
        return False
    total = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        number = int(char)
        if index % 2 == parity:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


class TaxIdentificationEngine:
    """Extract and validate SIREN/SIRET/VAT identifiers together."""

    ENGINE_NAME = "tax_identification"

    def extract(self, text: str) -> dict[str, Any]:
        siret_candidates = unique(re.findall(r"\b\d{3}\s?\d{3}\s?\d{3}\s?\d{5}\b", text), limit=30)
        raw_siren_candidates = unique(re.findall(r"\b\d{3}\s?\d{3}\s?\d{3}\b", text), limit=40)
        vat_candidates = unique(
            re.findall(r"\bFR\s?[A-Z0-9]{2}(?:\s?\d){9,12}\b", text, flags=re.IGNORECASE),
            limit=30,
        )

        siren_candidates: list[str] = []
        for siret in siret_candidates:
            siren = only_digits(siret)[:9]
            if len(siren) == 9 and siren not in siren_candidates:
                siren_candidates.append(siren)
        for value in raw_siren_candidates:
            siren = only_digits(value)
            if len(siren) == 9 and siren not in siren_candidates:
                siren_candidates.append(siren)

        valid_sirens = [siren for siren in siren_candidates if is_luhn_valid(siren)]
        sirens_for_vat = valid_sirens or siren_candidates
        expected_by_siren = {
            siren: expected
            for siren in sirens_for_vat
            if (expected := french_vat_from_siren(siren))
        }

        validated_vats: list[str] = []
        rejected_vats: list[dict[str, Any]] = []
        normalized_seen: set[str] = set()
        for raw in vat_candidates:
            vat = normalize_french_vat(raw)
            if vat in normalized_seen:
                continue
            normalized_seen.add(vat)

            if not re.fullmatch(r"FR\d{11}", vat):
                rejected_vats.append({"value": raw, "normalized": vat, "reason": "format_invalide"})
                continue

            siren = vat[-9:]
            expected = french_vat_from_siren(siren)
            if expected != vat:
                rejected_vats.append(
                    {
                        "value": raw,
                        "normalized": vat,
                        "siren": siren,
                        "expected": expected,
                        "reason": "cle_tva_incoherente",
                    }
                )
                continue

            if expected_by_siren and siren not in expected_by_siren:
                rejected_vats.append(
                    {
                        "value": raw,
                        "normalized": vat,
                        "siren": siren,
                        "expected_from_detected_sirens": list(expected_by_siren.values())[:5],
                        "reason": "siren_non_detecte_dans_document",
                    }
                )
                continue

            validated_vats.append(vat)

        expected_vats = [vat for vat in expected_by_siren.values() if vat not in validated_vats]
        status = "valide" if validated_vats else "non_valide"
        if expected_vats and not validated_vats:
            status = "tva_attendue_depuis_siren"

        return {
            "engine": self.ENGINE_NAME,
            "status": status,
            "vat_numbers": validated_vats,
            "vat_candidates": vat_candidates,
            "rejected_vat_candidates": rejected_vats,
            "siret": siret_candidates,
            "siren": siren_candidates,
            "valid_siren": valid_sirens,
            "expected_vat_from_siren": expected_vats,
            "summary": compact_text(
                f"TVA valide: {', '.join(validated_vats) or 'aucune'}; "
                f"TVA attendue SIREN: {', '.join(expected_vats) or 'aucune'}"
            ),
        }
