from __future__ import annotations

import re

from app.config import get_config
from app.text_utils import fold_text

DEFAULT_STREET_TYPE_ABBREVIATIONS: dict[str, str] = {
    "av": "avenue",
    "bd": "boulevard",
    "rte": "route",
    "ch": "chemin",
    "all": "allee",
    "imp": "impasse",
    "pl": "place",
    "qu": "quai",
    "fbg": "faubourg",
    "faub": "faubourg",
    "pas": "passage",
    "crs": "cours",
    "sq": "square",
    "r": "rue",
}

DEFAULT_STREET_TYPE_WORDS: tuple[str, ...] = (
    "rue",
    "avenue",
    "boulevard",
    "route",
    "chemin",
    "allee",
    "impasse",
    "quai",
    "place",
    "zac",
    "za",
    "zi",
    "zone",
    "lieu dit",
    "lieudit",
    "faubourg",
    "passage",
    "cours",
    "square",
)


def street_type_abbreviations() -> dict[str, str]:
    configured = get_config().get("street_type_abbreviations") or {}
    merged = dict(DEFAULT_STREET_TYPE_ABBREVIATIONS)
    merged.update({fold_text(key).rstrip("."): fold_text(value) for key, value in configured.items()})
    return merged


def street_type_words() -> tuple[str, ...]:
    configured = get_config().get("street_type_words") or []
    if configured:
        return tuple(fold_text(item) for item in configured)
    return DEFAULT_STREET_TYPE_WORDS


def expand_street_type_abbreviations(value: str) -> str:
    from app.text_utils import normalize_address_compare

    text = normalize_address_compare(value)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\blieu[\s-]?dit\b", "lieu dit", text)

    for abbrev, full in sorted(street_type_abbreviations().items(), key=lambda item: len(item[0]), reverse=True):
        if abbrev == "r":
            text = re.sub(rf"\br\.(?=\s)", "rue ", text)
            continue
        text = re.sub(rf"\b{re.escape(abbrev)}\.(?=\s)", f"{full} ", text)
        text = re.sub(rf"\b{re.escape(abbrev)}\b(?=\s)", f"{full} ", text)

    return re.sub(r"\s+", " ", text).strip()


def street_type_padded_tokens() -> list[str]:
    return [f" {word} " for word in street_type_words()]


def street_type_regex_fragment() -> str:
    parts = [
        "lieu[\\s-]?dit",
        "lieudit",
        "avenue",
        r"av\.?",
        "boulevard",
        r"bd\.?",
        "route",
        r"rte\.?",
        "chemin",
        r"ch\.?",
        "allee",
        r"all\.?",
        "impasse",
        r"imp\.?",
        "quai",
        r"qu\.?",
        "place",
        r"pl\.?",
        "faubourg",
        r"fbg\.?",
        r"faub\.?",
        "passage",
        r"pas\.?",
        "cours",
        r"crs\.?",
        "square",
        r"sq\.?",
        "zac",
        "za",
        "zi",
        "zone",
        "rue",
        r"r\.(?=\s)",
    ]
    return "(?:" + "|".join(parts) + ")"


def normalize_street_for_match(value: str) -> str:
    from app.text_utils import norm_key

    return norm_key(expand_street_type_abbreviations(value))
