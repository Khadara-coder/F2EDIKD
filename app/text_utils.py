from __future__ import annotations

import re
import unicodedata


def fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def normalize_address_compare(value: str) -> str:
    """Fold accents and strip punctuation before address matching."""
    value = fold_text(value or "")
    value = re.sub(r"[,;:.\"'´`^°/\\|]+", " ", value)
    value = re.sub(r"[-_]+", " ", value)
    value = re.sub(r"[^\w\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def first_value(values: list[str]) -> str | None:
    return values[0] if values else None


def norm_name(value: str) -> str:
    return normalize_address_compare(value).upper()


def norm_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", norm_name(value))


def norm_vat(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").upper())


def norm_postal(value: str) -> str:
    value = (value or "").strip()
    return value.zfill(5) if value.isdigit() and len(value) <= 5 else value


def norm_order_key(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").upper())


def significant_tokens(value: str) -> list[str]:
    stop = {"A", "AU", "DE", "DES", "DU", "ET", "FRANCE", "GROUPE", "LA", "LE", "LES", "SA", "SAS", "SASU"}
    return [token for token in re.findall(r"[A-Z0-9]{3,}", norm_name(value)) if token not in stop]


def unique(values: list[str], limit: int = 20) -> list[str]:
    seen = set()
    results = []
    for value in values:
        cleaned = compact_text(value)
        key = fold_text(cleaned)
        if cleaned and key not in seen:
            seen.add(key)
            results.append(cleaned)
        if len(results) >= limit:
            break
    return results


def extract_postal_codes(text: str) -> list[str]:
    seen = set()
    results = []
    for match in re.finditer(r"\b(\d{5})\b", text):
        postal = norm_postal(match.group(1))
        if postal not in seen:
            seen.add(postal)
            results.append(postal)
    return results
