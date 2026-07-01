from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
DEFAULT_CONFIG_PATH = PROJECT_DIR / "config" / "extraction.yaml"

DEFAULTS: dict[str, Any] = {
    "scoring": {
        "buyer_min_score": 45,
        "buyer_min_margin": 10,
        "buyer_vat_auto_score": 140,
        "buyer_order_lookup_score": 200,
        "shipto_validated_min": 75,
        "street_exact_ratio": 0.88,
        "street_fuzzy_ratio": 0.68,
        "layout_geo_bonus_factor": 0.35,
        "layout_above_anchor_factor": 0.35,
        "layout_delivery_min_score": 75,
        "layout_billing_column_penalty": 45,
        "layout_delivery_column_bonus": 12,
        "layout_delivery_anchor_block_bonus": 25,
        "delivery_resolve_layout_min_score": 70,
        "shipto_min_margin": 15,
        "shipto_service_name_score": 40,
        "shipto_service_tokens_score": 30,
        "layout_require_closer_to_delivery": True,
        "layout_vocabulary_margin_norm": 0.01,
        "layout_ocr_relaxed_anchor_claim": True,
        "shipto_master_guided_min": 55,
    },
    "anchors": {
        "delivery": [],
        "delivery_exclude": [],
        "negative": [],
        "negative_exclude": [],
    },
    "postal_false_positive_patterns": [],
    "internal_company_addresses": [],
    "delivery_section_stop_words": [],
    "noise_lines": [],
    "section_stop_words": [],
    "ocr": {
        "min_native_text_chars": 30,
        "selective_crop_enabled": True,
        "selective_crop_top_ratio": 0.55,
        "selective_crop_margin_px": 12,
    },
    "pdf": {"max_pages_per_request": 8},
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    config = DEFAULTS
    config_path = Path(__file__).resolve().parents[1] / "config" / "extraction.yaml"
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        config = _deep_merge(DEFAULTS, loaded)
    return config


def scoring_config() -> dict[str, Any]:
    return get_config()["scoring"]
