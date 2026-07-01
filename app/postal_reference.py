from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.text_utils import compact_text, fold_text, norm_name, norm_postal, normalize_address_compare

_CITY_RE = r"[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ' -]{2,}"


def reference_path() -> Path:
    return Path(os.getenv("POSTAL_REFERENCE_PATH", "data/reference/fr_communes.json"))


def normalize_city(value: str | None) -> str:
    city = normalize_address_compare(value or "")
    city = re.sub(r"\b(?:cedex|cx)\b.*$", "", city).strip()
    return re.sub(r"\s+", " ", city)


def city_compatible(a: str, b: str) -> bool:
    a_key = normalize_city(a)
    b_key = normalize_city(b)
    if not a_key or not b_key:
        return False
    return a_key == b_key or a_key.startswith(b_key) or b_key.startswith(a_key)


@lru_cache(maxsize=1)
def load_postal_reference() -> dict[str, Any]:
    path = reference_path()
    result: dict[str, Any] = {
        "loaded": False,
        "path": str(path),
        "error": "",
        "communes_count": 0,
        "postal_count": 0,
        "postal_to_cities": {},
        "city_to_postals": {},
    }
    if not path.exists():
        result["error"] = "Postal reference missing"
        return result

    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        result["error"] = f"Unable to read postal reference: {exc}"
        return result

    postal_to_cities: dict[str, set[str]] = {}
    city_to_postals: dict[str, set[str]] = {}
    for row in rows if isinstance(rows, list) else []:
        city = normalize_city(row.get("nom") if isinstance(row, dict) else "")
        if not city:
            continue
        for postal in row.get("codesPostaux", []) or []:
            postal = norm_postal(postal)
            if postal:
                postal_to_cities.setdefault(postal, set()).add(city)
                city_to_postals.setdefault(city, set()).add(postal)

    result["loaded"] = True
    result["communes_count"] = len(rows) if isinstance(rows, list) else 0
    result["postal_count"] = len(postal_to_cities)
    result["postal_to_cities"] = {postal: sorted(cities) for postal, cities in postal_to_cities.items()}
    result["city_to_postals"] = {city: sorted(postals) for city, postals in city_to_postals.items()}
    return result


def validate_postal_city(postal: str | None, city: str | None) -> dict[str, Any]:
    postal = norm_postal(postal or "")
    city = city or ""
    reference = load_postal_reference()
    if not postal or not city:
        return {"status": "incomplet", "match": None, "reference_loaded": reference["loaded"]}
    if not reference["loaded"]:
        return {
            "status": "reference_absente",
            "match": None,
            "reference_loaded": False,
            "reason": reference.get("error", ""),
        }

    expected = reference["postal_to_cities"].get(postal, [])
    if not expected:
        city_postals: list[str] = []
        for known_city, postals in reference.get("city_to_postals", {}).items():
            if city_compatible(city, known_city):
                city_postals.extend(postals)
        if city_postals and postal.isdigit() and len(postal) == 5:
            department = postal[:2]
            if any(item[:2] == department for item in city_postals):
                matched_city = norm_name(city)
                return {
                    "status": "cedex_ok",
                    "match": True,
                    "expected_cities": sorted(set(city_postals))[:8],
                    "matched_city": matched_city,
                }
        return {"status": "code_postal_inconnu", "match": False, "expected_cities": []}

    for expected_city in expected:
        if city_compatible(city, expected_city):
            return {"status": "ok", "match": True, "expected_cities": expected[:8], "matched_city": expected_city.upper()}

    return {
        "status": "ville_incompatible",
        "match": False,
        "expected_cities": expected[:8],
    }


def postals_for_city(city: str | None) -> list[str]:
    reference = load_postal_reference()
    if not reference["loaded"] or not city:
        return []
    city_key = normalize_city(city)
    if not city_key:
        return []
    direct = reference.get("city_to_postals", {}).get(city_key, [])
    if direct:
        return list(direct)
    for known_city, postals in reference.get("city_to_postals", {}).items():
        if city_compatible(city_key, known_city):
            return list(postals)
    return []


def find_city_mentions(text: str, *, min_length: int = 4) -> list[dict[str, Any]]:
    reference = load_postal_reference()
    folded = normalize_city(text)
    if not reference["loaded"] or not folded:
        return []
    matches = []
    for city, postals in reference.get("city_to_postals", {}).items():
        if len(city) < min_length:
            continue
        if re.search(rf"(?<![a-z]){re.escape(city)}(?![a-z])", folded):
            matches.append({"city": city, "postals": list(postals)})
    matches.sort(key=lambda item: len(item["city"]), reverse=True)
    return matches


def is_postal_form_field_line(text: str) -> bool:
    try:
        from app.config import get_config

        folded = fold_text(text)
        for pattern in get_config().get("postal_false_positive_patterns", []):
            if re.search(pattern, folded, flags=re.IGNORECASE):
                return True
    except Exception:
        pass
    return False


def is_acceptable_postal_city_validation(validation: dict[str, Any] | None) -> bool:
    if not validation:
        return False
    if validation.get("match") is True:
        return True
    return validation.get("status") in {"ville_incompatible", "cedex_ok"}


def is_rejectable_postal_city_pair(
    postal: str | None,
    city: str | None,
    validation: dict[str, Any] | None = None,
    *,
    street: str | None = None,
) -> bool:
    if not postal or not city:
        return True
    if is_invalid_city_token(city, street=street):
        return True
    validation = validation or validate_postal_city(postal, city)
    return not is_acceptable_postal_city_validation(validation)


def invalid_city_tokens() -> frozenset[str]:
    try:
        from app.config import get_config

        tokens = get_config().get("postal_invalid_city_tokens", [])
    except Exception:
        tokens = []
    return frozenset(fold_text(token) for token in tokens if token)


def is_invalid_city_token(city: str | None, *, street: str | None = None) -> bool:
    city_key = normalize_city(city or "")
    if not city_key or len(city_key) < 3:
        return True
    if city_key in invalid_city_tokens():
        return True
    street_key = normalize_city(street or "")
    if street_key and city_key and street_key.startswith(f"{city_key} "):
        return True
    return False


def clean_city_fragment(raw: str | None) -> str:
    city = compact_text(raw or "")
    if not city:
        return ""
    city = compact_text(re.split(r"\s{2,}|\s+-\s+|[,;|]", city, maxsplit=1)[0])
    return norm_name(city)


def infer_city_from_postal(postal: str | None) -> str | None:
    reference = load_postal_reference()
    postal = norm_postal(postal or "")
    if not reference["loaded"] or not postal:
        return None
    cities = reference["postal_to_cities"].get(postal, [])
    if len(cities) == 1:
        return cities[0].upper()
    return None


def postal_form_prefix_patterns() -> list[str]:
    try:
        from app.config import get_config

        patterns = get_config().get("postal_form_prefix_patterns", [])
    except Exception:
        patterns = []
    if patterns:
        return list(patterns)
    return [
        r"^devise[.\s]+",
        r"^type\s+livraison[.\s]+",
        r"^livre\s+",
        r"^depot[.\s+]+",
        r"^dépot[.\s+]+",
        r"^depot[.\s+]+",
    ]


def normalize_postal_extraction_text(text: str) -> str:
    value = compact_text(text)
    for pattern in postal_form_prefix_patterns():
        value = re.sub(pattern, "", value, flags=re.IGNORECASE).strip(" -:;.")
    return compact_text(value)


def postal_extraction_text_variants(text: str) -> list[str]:
    value = compact_text(text)
    if not value:
        return []
    variants = [value]
    stripped = normalize_postal_extraction_text(value)
    if stripped and stripped not in variants:
        variants.append(stripped)
    return variants


def extract_postal_city_pairs(text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    original = compact_text(text)
    form_field_source = is_postal_form_field_line(original)

    for value in postal_extraction_text_variants(text):
        if value == original and form_field_source:
            stripped = normalize_postal_extraction_text(value)
            if not stripped or stripped == value:
                continue
        if not value:
            continue
        results.extend(
            _extract_postal_city_pairs_from_line(
                value,
                seen,
                is_stripped=value != original,
                allow_infer=not form_field_source,
            )
        )
    return results


def _extract_postal_city_pairs_from_line(
    value: str,
    seen: set[tuple[str, str]],
    *,
    is_stripped: bool = False,
    allow_infer: bool = True,
) -> list[dict[str, Any]]:
    if not value or (is_postal_form_field_line(value) and not is_stripped):
        return []

    results: list[dict[str, Any]] = []
    patterns: list[tuple[str, str]] = [
        ("spaced", rf"(\d{{2}})\s+(\d{{3}})\s*({_CITY_RE})?"),
        ("standard", rf"\b(\d{{5}})\s*({_CITY_RE})?"),
        ("glued", rf"\b(\d{{5}})({_CITY_RE})"),
        ("negative_glued", rf"-(\d{{5}})({_CITY_RE})"),
    ]

    for source, pattern in patterns:
        for match in re.finditer(pattern, value, flags=re.IGNORECASE):
            if source == "spaced":
                postal = norm_postal(match.group(1) + match.group(2))
                city_raw = match.group(3)
            else:
                postal = norm_postal(match.group(1))
                city_raw = match.group(2)

            if not postal.isdigit() or len(postal) != 5:
                continue

            city = clean_city_fragment(city_raw)
            if is_invalid_city_token(city):
                city = ""

            key = (postal, city)
            if key in seen:
                continue
            seen.add(key)

            if not city and allow_infer:
                inferred = infer_city_from_postal(postal)
                if inferred and not is_postal_form_field_line(value):
                    city = inferred

            validation = validate_postal_city(postal, city) if city else {"match": None, "status": "incomplet"}
            results.append(
                {
                    "postal": postal,
                    "city": city,
                    "validation": validation,
                    "match": validation.get("match"),
                    "start": match.start(),
                    "source": source,
                }
            )
    return results


def best_valid_postal_city_pair(text: str) -> dict[str, Any] | None:
    pairs = [
        item
        for item in extract_postal_city_pairs(text)
        if item.get("city") and is_acceptable_postal_city_validation(item.get("validation"))
    ]
    if not pairs:
        return None

    folded = normalize_city(text)
    folded_raw = fold_text(text)
    best: dict[str, Any] | None = None
    best_score = -1
    for pair in pairs:
        city_key = normalize_city(pair["city"])
        city_match = re.search(rf"(?<![a-z]){re.escape(city_key)}(?![a-z])", folded) if city_key else None
        postal_match = re.search(rf"\b{re.escape(pair['postal'])}\b", folded)
        if not postal_match and pair["source"] in {"spaced", "negative_glued"}:
            postal_match = re.search(
                rf"\b{re.escape(pair['postal'][:2])}\s+{re.escape(pair['postal'][2:])}\b",
                folded_raw,
            )
        if not postal_match and pair["source"] in {"glued", "negative_glued"}:
            postal_match = re.search(rf"{re.escape(pair['postal'])}{re.escape(city_key)}", folded)
        distance = abs(postal_match.start() - city_match.start()) if postal_match and city_match else 999
        score = 1000 - distance + len(pair["city"])
        if score > best_score:
            best_score = score
            best = {
                "postal": pair["postal"],
                "city": pair["city"],
                "distance": distance,
                "source": "postal_city_text",
            }
    return best


def choose_best_postal_city_from_line(line: str) -> tuple[str, str] | None:
    pair = best_valid_postal_city_pair(line)
    if not pair:
        return None
    return pair["postal"], pair["city"]


def best_postal_city_in_text(text: str) -> dict[str, Any] | None:
    pair = best_valid_postal_city_pair(text)
    if pair:
        return pair

    folded = normalize_city(text)
    if not folded:
        return None
    postal_matches = list(re.finditer(r"\b(\d{4,5})\b", folded))
    city_mentions = find_city_mentions(text)
    best: dict[str, Any] | None = None
    best_score = -1

    for mention in city_mentions:
        city = mention["city"]
        city_match = re.search(rf"(?<![a-z]){re.escape(city)}(?![a-z])", folded)
        if not city_match:
            continue
        for postal_match in postal_matches:
            postal = norm_postal(postal_match.group(1))
            if postal not in mention["postals"]:
                continue
            validation = validate_postal_city(postal, city.upper())
            if validation.get("match") is not True:
                continue
            distance = abs(postal_match.start() - city_match.start())
            score = 1000 - distance + len(city)
            if score > best_score:
                best_score = score
                best = {
                    "postal": postal,
                    "city": city.upper(),
                    "distance": distance,
                    "source": "postal_city_text",
                }
    return best
