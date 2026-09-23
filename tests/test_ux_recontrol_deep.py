"""Exhaustive test coverage of src.ux_recontrol.can_close_after_recontrol.

The base test file (tests/test_ux_recontrol.py) sketches the three broad
categories (header, EDI/technical, line). This file pins the behaviour code
by code and exercises the edge cases that are easy to break on refactor:

  - normalisation of the rejection code (case, aliases via rejection_catalog)
  - "empty string" vs "missing" vs "whitespace only" as blank sentinels
  - line-level rechecks require the RIGHT shape (quantity as int / str / None)
  - EDI and MASTERDATA codes are intentionally *not* closable by a click
  - delivery codes need sapSentAt to be truthy
  - unknown codes always return False (fail closed)
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ux_recontrol import can_close_after_recontrol  # noqa: E402


def _review(**overrides):
    base = {
        "order": {
            "customerOrderNumber": "",
            "orderDate": None,
            "requestedDeliveryDate": None,
            "sapSentAt": None,
        },
        "partners": [
            {"partnerFunction": "soldto", "partnerCode": ""},
            {"partnerFunction": "shipto", "partnerCode": ""},
        ],
        "lines": [],
        "edifactReady": False,
    }
    base.update(overrides)
    return base


# ─── ORDER-level rechecks ─────────────────────────────────────────────────

@pytest.mark.parametrize(
    "code,order,expected",
    [
        # ORDER_KEY_MISSING closes when customerOrderNumber has any non-empty value
        ("ORDER_KEY_MISSING", {"customerOrderNumber": "PO-42"}, True),
        ("ORDER_KEY_MISSING", {"customerOrderNumber": ""}, False),
        ("ORDER_KEY_MISSING", {"customerOrderNumber": None}, False),
        ("ORDER_KEY_MISSING", {"customerOrderNumber": "   "}, False),  # whitespace stripped
        ("ORDER_KEY_MISSING", {"customerOrderNumber": "0"}, True),  # "0" is legit
        # ORDER_DATE_INVALID: any truthy orderDate closes
        ("ORDER_DATE_INVALID", {"orderDate": "2026-09-21"}, True),
        ("ORDER_DATE_INVALID", {"orderDate": None}, False),
        ("ORDER_DATE_INVALID", {"orderDate": ""}, False),
        # DELIVERY_DATE_INVALID
        ("DELIVERY_DATE_INVALID", {"requestedDeliveryDate": "2026-10-01"}, True),
        ("DELIVERY_DATE_INVALID", {"requestedDeliveryDate": None}, False),
    ],
)
def test_order_level_rechecks(code, order, expected):
    review = _review(order={**_review()["order"], **order})
    assert can_close_after_recontrol(code, review) is expected


# ─── PARTNER-level rechecks ───────────────────────────────────────────────

@pytest.mark.parametrize(
    "code",
    [
        "SOLDTO_NOT_FOUND",
        "SOLDTO_AMBIGUOUS_MATCH",
    ],
)
def test_soldto_codes_close_when_soldto_code_is_set(code):
    ok = _review(partners=[
        {"partnerFunction": "soldto", "partnerCode": "1000"},
        {"partnerFunction": "shipto", "partnerCode": ""},
    ])
    empty = _review(partners=[
        {"partnerFunction": "soldto", "partnerCode": ""},
        {"partnerFunction": "shipto", "partnerCode": ""},
    ])
    whitespace = _review(partners=[
        {"partnerFunction": "soldto", "partnerCode": "   "},
        {"partnerFunction": "shipto", "partnerCode": ""},
    ])

    assert can_close_after_recontrol(code, ok) is True
    assert can_close_after_recontrol(code, empty) is False
    assert can_close_after_recontrol(code, whitespace) is False


@pytest.mark.parametrize(
    "code",
    [
        "NO_DELIVERY_ADDRESS",
        "SHIPTO_CANDIDATES_MISSING",
        "SHIPTO_NO_STRONG_MATCH",
        "SHIPTO_AMBIGUOUS_MATCH",
        "SHIPTO_SOLDTO_MISMATCH",
        "PARTNER_UNRESOLVED",
    ],
)
def test_shipto_codes_close_when_shipto_code_is_set(code):
    ok = _review(partners=[
        {"partnerFunction": "soldto", "partnerCode": "1000"},
        {"partnerFunction": "shipto", "partnerCode": "2000"},
    ])
    empty = _review(partners=[
        {"partnerFunction": "soldto", "partnerCode": "1000"},
        {"partnerFunction": "shipto", "partnerCode": ""},
    ])

    assert can_close_after_recontrol(code, ok) is True
    assert can_close_after_recontrol(code, empty) is False


def test_partner_lookup_uses_partner_function_key_not_order():
    # If the partner list is empty, shipto/soldto lookup returns {} and the
    # code should not close. This is the classic "review payload missing
    # partner data" trap.
    review = _review(partners=[])
    for code in [
        "SOLDTO_NOT_FOUND",
        "NO_DELIVERY_ADDRESS",
        "SHIPTO_CANDIDATES_MISSING",
        "PARTNER_UNRESOLVED",
    ]:
        assert can_close_after_recontrol(code, review) is False


# ─── LINE-level rechecks ──────────────────────────────────────────────────

@pytest.mark.parametrize("code", ["NO_LINE_ITEMS", "NO_VALID_ARTICLE"])
def test_line_presence_codes_close_when_at_least_one_line_exists(code):
    empty = _review(lines=[])
    one_line = _review(lines=[{"boschArticle": "A-1", "quantity": 1}])
    assert can_close_after_recontrol(code, empty) is False
    assert can_close_after_recontrol(code, one_line) is True


@pytest.mark.parametrize("code", ["QUANTITY_MISSING", "ARTICLE_QUANTITY_INVALID"])
def test_quantity_codes_close_when_any_line_has_positive_quantity(code):
    zero_only = _review(lines=[{"quantity": 0}])
    negative_only = _review(lines=[{"quantity": -3}])
    mixed = _review(lines=[{"quantity": 0}, {"quantity": 2.5}, {"quantity": None}])
    all_none = _review(lines=[{"quantity": None}, {"quantity": None}])

    assert can_close_after_recontrol(code, zero_only) is False
    assert can_close_after_recontrol(code, negative_only) is False
    assert can_close_after_recontrol(code, mixed) is True  # at least one > 0 → closes
    assert can_close_after_recontrol(code, all_none) is False


def test_quantity_accepts_stringified_numbers():
    review = _review(lines=[{"quantity": "3.5"}])
    assert can_close_after_recontrol("QUANTITY_MISSING", review) is True


def test_quantity_ignores_non_numeric_junk():
    review = _review(lines=[{"quantity": "N/A"}, {"quantity": "abc"}])
    assert can_close_after_recontrol("QUANTITY_MISSING", review) is False


@pytest.mark.parametrize("code", ["ARTICLE_NOT_FOUND", "MATERIAL_STATUS_INVALID"])
def test_article_codes_close_when_any_line_has_a_bosch_article(code):
    without = _review(lines=[{"boschArticle": "", "quantity": 1}])
    with_article = _review(lines=[{"boschArticle": "A-42", "quantity": 1}])
    whitespace = _review(lines=[{"boschArticle": "   ", "quantity": 1}])
    assert can_close_after_recontrol(code, without) is False
    assert can_close_after_recontrol(code, with_article) is True
    assert can_close_after_recontrol(code, whitespace) is False


# ─── EDI + technical codes — deliberately NOT closable by a click ─────────

@pytest.mark.parametrize(
    "code",
    [
        "EDIFACT_MISSING_BGM",
        "EDIFACT_MISSING_DTM_137",
        "EDIFACT_MISSING_NAD_BY",
        "EDIFACT_MISSING_NAD_DP",
        "EDIFACT_MISSING_LIN",
        "EDIFACT_LINE_INTEGRITY_MISMATCH",
        "EDIFACT_NAD_DP_MISMATCH",
    ],
)
def test_edi_codes_require_edifact_ready_flag(code):
    off = _review(edifactReady=False)
    on = _review(edifactReady=True)
    assert can_close_after_recontrol(code, off) is False
    assert can_close_after_recontrol(code, on) is True


@pytest.mark.parametrize("code", ["MASTERDATA_MISSING", "MASTERDATA_SCHEMA_INVALID"])
def test_masterdata_codes_never_close_from_a_review_check(code):
    # These are SYSTEM-resolution codes; the review payload cannot fix them
    # by construction, so can_close_after_recontrol always returns False.
    for review in [_review(), _review(edifactReady=True), _review(lines=[{"quantity": 5}])]:
        assert can_close_after_recontrol(code, review) is False


# ─── Delivery codes — depend on sapSentAt ─────────────────────────────────

@pytest.mark.parametrize("code", ["DELIVERY_SFTP_FAILED", "DELIVERY_EMAIL_FAILED"])
def test_delivery_codes_close_when_sap_sent_at_is_set(code):
    review_pending = _review(order={**_review()["order"], "sapSentAt": None})
    review_sent = _review(order={**_review()["order"], "sapSentAt": "2026-09-21T10:00:00Z"})
    assert can_close_after_recontrol(code, review_pending) is False
    assert can_close_after_recontrol(code, review_sent) is True


# ─── Case sensitivity + aliases ───────────────────────────────────────────

def test_code_matching_is_case_sensitive_after_normalization():
    # normalize_code() only strips whitespace and applies alias remapping;
    # it does NOT uppercase. The `can_close_after_recontrol` branches use
    # exact string equality on the CANONICAL uppercase codes emitted by
    # the rejection engine, so a lowercase input from outside must not
    # short-circuit them.
    review = _review(order={**_review()["order"], "customerOrderNumber": "PO-1"})
    assert can_close_after_recontrol("order_key_missing", review) is False
    assert can_close_after_recontrol("ORDER_KEY_MISSING", review) is True


def test_code_is_stripped_before_matching():
    # Leading/trailing whitespace is trimmed by normalize_code.
    review = _review(order={**_review()["order"], "customerOrderNumber": "PO-1"})
    assert can_close_after_recontrol("  ORDER_KEY_MISSING  ", review) is True


# ─── Unknown / unhandled codes ────────────────────────────────────────────

def test_unknown_code_returns_false():
    assert can_close_after_recontrol("SOMETHING_ELSE_ENTIRELY", _review()) is False


def test_empty_code_returns_false():
    # An empty rejection code should not accidentally match a branch.
    assert can_close_after_recontrol("", _review()) is False


# ─── Defensive: bad review shape doesn't crash ────────────────────────────

def test_none_review_fields_do_not_raise():
    review = {"order": None, "partners": None, "lines": None}
    # Should return False rather than crash on `.get()` chains.
    for code in [
        "ORDER_KEY_MISSING",
        "SOLDTO_NOT_FOUND",
        "NO_LINE_ITEMS",
        "QUANTITY_MISSING",
        "DELIVERY_SFTP_FAILED",
    ]:
        assert can_close_after_recontrol(code, review) is False


# ─── Product decision (2026-09-23): recontrol trusts the ADV ─────────────
# The ADV validation truth table (row 12) mentions "référence finale valide
# après recontrôle", but product asked to keep the recontrol permissive:
# the ADV's click is the record, no hard field-check blocks the auto-close.
# The pipeline enforces real integrity downstream at EDIFACT generation and
# SFTP delivery — the anomaly state is a UX signal, not a compliance gate.


def test_material_status_recontrol_accepts_any_non_empty_reference():
    # By design: an ADV who typed anything into the article field closes the
    # anomaly. Real validation happens at EDIFACT generation time.
    review = _review(lines=[{"boschArticle": "TYPED-BY-ADV"}])
    assert can_close_after_recontrol("MATERIAL_STATUS_INVALID", review) is True
