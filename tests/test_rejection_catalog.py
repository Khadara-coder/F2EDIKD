"""Tests for src/rejection_catalog.py.

Run from /tmp copy to avoid FUSE __pycache__ limit:
  cp -r /Workspace/Users/rsr1dy@bosch.com/EDIFACT /tmp/t
  cd /tmp/t && python -m pytest tests/test_rejection_catalog.py -v -p no:cacheprovider
"""
import pytest
import sys
import os

# Allow importing src/ directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import rejection_catalog as rc  # noqa: E402


# Required codes specified in the production blueprint
REQUIRED_CODES = {
    "PDF_PARSE_FAILURE", "NOT_A_PDF", "ORDER_KEY_MISSING", "NO_VALID_ARTICLE",
    "CONTRACT_KEYWORD", "CONTRACT_BREAK_ADDRESSES_MISSING",
    "CONTRACT_BREAK_ARTICLES_MISSING", "CONTRACT_BREAK_SOLDTO_MISSING",
    "CONTRACT_BREAK_SHIPTO_CANDIDATES_MISSING",
    "SOLDTO_NOT_FOUND", "SOLDTO_AMBIGUOUS_MATCH",
    "SHIPTO_WEAK_EVIDENCE_IN_SOLDTO_FAMILY", "SHIPTO_NO_STRONG_MATCH",
    "SHIPTO_AMBIGUOUS_MATCH",
    "EDIFACT_MISSING_BGM", "EDIFACT_MISSING_DTM_137",
    "EDIFACT_MISSING_NAD_BY", "EDIFACT_MISSING_NAD_DP", "EDIFACT_MISSING_LIN",
    "ARTICLE_QUANTITY_INVALID", "UNIT_PRICE_MISSING",
    "EDIFACT_LINE_INTEGRITY_MISMATCH", "EDIFACT_NAD_DP_MISMATCH",
    "DUPLICATE_ALREADY_SENT", "DELIVERY_SFTP_FAILED", "DELIVERY_EMAIL_FAILED",
}


def test_rejection_catalog_has_required_codes():
    missing = REQUIRED_CODES - set(rc.REJECTION_CATALOG.keys())
    assert not missing, f"Missing codes: {missing}"


def test_all_entries_have_required_fields():
    required_fields = {
        "severity", "business_status", "retry_allowed",
        "manual_review_required", "message_fr", "message_en",
    }
    for code, entry in rc.REJECTION_CATALOG.items():
        missing = required_fields - set(entry.keys())
        assert not missing, f"{code} missing fields: {missing}"


def test_severity_values_are_canonical():
    valid = {"BLOCKER", "BUSINESS_REJECT", "TECHNICAL", "UNKNOWN"}
    for code, entry in rc.REJECTION_CATALOG.items():
        assert entry["severity"] in valid, \
            f"{code} has invalid severity: {entry['severity']}"


def test_business_status_values_are_canonical():
    valid = {"REJECTED", "DUPLICATE", "DELIVERY_FAILED", "PENDING_USER_INPUT"}
    for code, entry in rc.REJECTION_CATALOG.items():
        assert entry["business_status"] in valid, \
            f"{code} has invalid business_status: {entry['business_status']}"


def test_get_returns_entry_for_known_code():
    entry = rc.get("ORDER_KEY_MISSING")
    assert entry["severity"] == "BUSINESS_REJECT"
    assert entry["business_status"] == "PENDING_USER_INPUT"
    assert entry["retry_allowed"] is True


def test_get_returns_fallback_for_unknown_code():
    entry = rc.get("TOTALLY_UNKNOWN_CODE")
    assert entry["severity"] == "UNKNOWN"
    assert "TOTALLY_UNKNOWN_CODE" in entry["message_en"]


def test_shipto_street_only_is_blocker():
    """Street-only SHIP-TO evidence must always be a BLOCKER."""
    entry = rc.get("SHIPTO_WEAK_EVIDENCE_IN_SOLDTO_FAMILY")
    assert entry["severity"] == "BLOCKER"
    assert entry["retry_allowed"] is False


def test_duplicate_already_sent_not_retryable():
    entry = rc.get("DUPLICATE_ALREADY_SENT")
    assert entry["retry_allowed"] is False
    assert entry["business_status"] == "DUPLICATE"


def test_action_text_returns_string_for_known_code():
    text = rc.action_text("PDF_PARSE_FAILURE", lang="fr")
    assert isinstance(text, str) and len(text) > 5


def test_action_text_returns_default_for_unknown():
    text = rc.action_text("DEFINITELY_NOT_REAL", lang="fr")
    assert "BI" in text or "équipe" in text


def test_messages_not_empty():
    for code, entry in rc.REJECTION_CATALOG.items():
        assert entry["message_fr"].strip(), f"{code} has empty message_fr"
        assert entry["message_en"].strip(), f"{code} has empty message_en"


def test_no_kinetix_in_catalog():
    """The word 'KINETIX' must never appear as a real value in the catalog."""
    for code, entry in rc.REJECTION_CATALOG.items():
        for field, val in entry.items():
            if isinstance(val, str):
                assert "KINETIX" not in val.upper() or "NEVER" in val.upper(), \
                    f"{code}.{field} references KINETIX as a value"
