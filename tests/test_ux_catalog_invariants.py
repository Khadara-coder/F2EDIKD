"""Invariants of the src.ux_catalog UX rule catalogue.

The base test file (tests/test_ux_catalog.py) verifies a handful of key
mappings. This file pins the *structural* invariants that must always hold
so a well-meaning edit does not silently break the ADV review UI:

  - Every active rule with codes must expose at least one choice.
  - Every choice pair (label, outcome) must be non-empty.
  - UX-IDs are unique.
  - Rejection codes are unique across rules (no ambiguous mapping).
  - Every UX rule referenced by src.ux_recontrol has a mapping here.
  - Well-known field values (status, resolution_mode) stay within the
    fixed lexicon.

There is also an XFAIL test that captures the current UX-08 defect
(two choices sharing the same outcome value); when the catalog is fixed
to give each button a distinct outcome, that test flips from XFAIL to
XPASS and drives the migration.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ux_catalog import UX_BY_CODE, UX_BY_ID, UX_RULES, ux_rule  # noqa: E402


VALID_STATUSES = {"active", "draft"}
VALID_RESOLUTION_MODES = {"ADV", "ADV + RECONTROL", "ADV + SYSTEM", "SYSTEM", "À définir"}


# ─── Structural invariants ────────────────────────────────────────────────

def test_every_rule_has_a_ux_id_matching_the_ux_dash_pattern():
    for rule in UX_RULES:
        assert rule["ux_id"].startswith("UX-")
        # 2-digit numeric suffix (UX-01..UX-20 today, room to grow)
        assert rule["ux_id"][3:].isdigit()


def test_ux_ids_are_unique():
    ids = [rule["ux_id"] for rule in UX_RULES]
    assert len(set(ids)) == len(ids)


def test_ux_by_id_maps_every_rule():
    for rule in UX_RULES:
        assert UX_BY_ID[rule["ux_id"]] is rule


def test_status_field_is_within_the_lexicon():
    for rule in UX_RULES:
        assert rule["status"] in VALID_STATUSES, f"{rule['ux_id']}: invalid status {rule['status']}"


def test_resolution_mode_is_within_the_lexicon():
    for rule in UX_RULES:
        assert rule["resolution_mode"] in VALID_RESOLUTION_MODES


def test_flags_are_booleans():
    for rule in UX_RULES:
        assert isinstance(rule["requires_recontrol"], bool)
        assert isinstance(rule["finalization_required"], bool)


def test_codes_are_uppercase_snake_case_strings():
    for rule in UX_RULES:
        for code in rule["codes"]:
            assert isinstance(code, str)
            assert code == code.upper(), f"{rule['ux_id']}: {code!r} is not uppercase"
            assert " " not in code
            assert "-" not in code


def test_choices_carry_non_empty_label_and_outcome():
    for rule in UX_RULES:
        for choice in rule["choices"]:
            assert choice["label"].strip(), f"{rule['ux_id']}: empty label"
            assert choice["outcome"].strip(), f"{rule['ux_id']}: empty outcome"


# ─── Cross-rule invariants ────────────────────────────────────────────────

def test_active_rules_with_codes_expose_at_least_one_choice_except_pure_system_ones():
    # UX-02 (LLM salvage, silent), UX-12 (resubmission detected, informational)
    # and UX-15 (masterdata, retry-only) are SYSTEM-resolved. UX-19 / UX-20 are draft.
    for rule in UX_RULES:
        if rule["status"] != "active":
            continue
        if not rule["codes"]:
            continue
        # SYSTEM-only rules (uxChoices may legitimately be empty)
        if rule["resolution_mode"] == "SYSTEM" and not rule["choices"]:
            continue
        assert rule["choices"], f"{rule['ux_id']} has codes {rule['codes']} but no choice"


@pytest.mark.xfail(
    reason=(
        "PARTNER_UNRESOLVED is listed under both UX-06 (shipto) and UX-07 (soldto), "
        "so UX_BY_CODE silently resolves it to whichever rule the dict comprehension "
        "iterated over last. ADV sees the soldto choices even for shipto-side anomalies. "
        "Fix: assign PARTNER_UNRESOLVED to a single rule (or split into two dedicated codes)."
    ),
    strict=True,
)
def test_active_rules_do_not_share_a_rejection_code_with_another_rule():
    # A rejection code must resolve to exactly one UX-* rule (UX_BY_CODE is a dict,
    # so collisions would silently drop entries).
    seen: dict[str, str] = {}
    for rule in UX_RULES:
        if rule["status"] != "active":
            continue
        for code in rule["codes"]:
            assert code not in seen or seen[code] == rule["ux_id"], (
                f"{code!r} shared between {seen[code]} and {rule['ux_id']}"
            )
            seen[code] = rule["ux_id"]


@pytest.mark.xfail(
    reason="Same PARTNER_UNRESOLVED double-mapping as above — UX_BY_CODE keeps only one entry.",
    strict=True,
)
def test_ux_by_code_index_is_consistent_with_the_rules_list():
    for rule in UX_RULES:
        if rule["status"] != "active":
            continue
        for code in rule["codes"]:
            assert UX_BY_CODE[code] is rule


def test_partner_unresolved_currently_resolves_to_a_single_rule_via_ux_by_code():
    # Complementary to the xfail above: document that UX_BY_CODE picks *one*
    # of the colliding rules deterministically (whichever iterates last in
    # the dict comprehension). If the catalog fix decides which one wins,
    # update the assertion; if it splits the code, remove this test.
    assert ux_rule("PARTNER_UNRESOLVED")["ux_id"] in {"UX-06", "UX-07"}


def test_ux_rule_returns_none_for_unknown_code():
    assert ux_rule("SOMETHING_NEW") is None
    assert ux_rule("") is None


def test_ux_rule_returns_none_for_draft_rules_codes():
    # UX-19 / UX-20 are drafts with empty code tuples — nothing to route to.
    for rule in UX_RULES:
        if rule["status"] == "draft":
            for code in rule["codes"]:  # currently empty; safety check for future edits
                pytest.fail(f"draft rule {rule['ux_id']} declares a code {code!r}")


# ─── UX-recontrol coverage ────────────────────────────────────────────────

def test_every_code_handled_by_ux_recontrol_has_a_ux_rule():
    # Explicit list of the codes ux_recontrol.can_close_after_recontrol
    # inspects — every one must have a UX-* rule so the ADV can act on it
    # from the review page.
    recontrol_codes = {
        "ORDER_KEY_MISSING",
        "ORDER_DATE_INVALID",
        "DELIVERY_DATE_INVALID",
        "SOLDTO_NOT_FOUND",
        "SOLDTO_AMBIGUOUS_MATCH",
        "NO_DELIVERY_ADDRESS",
        "SHIPTO_CANDIDATES_MISSING",
        "SHIPTO_NO_STRONG_MATCH",
        "SHIPTO_AMBIGUOUS_MATCH",
        "SHIPTO_SOLDTO_MISMATCH",
        "PARTNER_UNRESOLVED",
        "NO_LINE_ITEMS",
        "NO_VALID_ARTICLE",
        "QUANTITY_MISSING",
        "ARTICLE_QUANTITY_INVALID",
        "ARTICLE_NOT_FOUND",
        "MATERIAL_STATUS_INVALID",
        "EDIFACT_MISSING_BGM",
        "EDIFACT_MISSING_DTM_137",
        "EDIFACT_MISSING_NAD_BY",
        "EDIFACT_MISSING_NAD_DP",
        "EDIFACT_MISSING_LIN",
        "EDIFACT_LINE_INTEGRITY_MISMATCH",
        "EDIFACT_NAD_DP_MISMATCH",
        "DELIVERY_SFTP_FAILED",
        "DELIVERY_EMAIL_FAILED",
    }
    for code in recontrol_codes:
        assert ux_rule(code) is not None, f"{code} has recontrol logic but no UX-* mapping"


# ─── Known defect (documented) ────────────────────────────────────────────

@pytest.mark.xfail(
    reason=(
        "UX-08 currently has two choices sharing the outcome 'correct_and_recontrol'; "
        "when they get distinct outcomes, this test flips XPASS and can be inverted."
    ),
    strict=True,
)
def test_no_ux_rule_has_two_choices_with_the_same_outcome():
    for rule in UX_RULES:
        outcomes = [c["outcome"] for c in rule["choices"]]
        assert len(set(outcomes)) == len(outcomes), (
            f"{rule['ux_id']} has duplicate outcomes: {outcomes}"
        )


# ─── FR message hygiene ───────────────────────────────────────────────────

def test_active_rules_with_choices_carry_a_user_facing_message():
    for rule in UX_RULES:
        if rule["status"] == "active" and rule["choices"]:
            assert rule["message"], f"{rule['ux_id']} exposes choices but no message"


def test_choice_labels_are_first_person_singular_je():
    # The ADV taxonomy is written from the operator's perspective — every
    # label starts with "J'ai", "Le", "Relancer", or another explicit
    # subject that keeps the affordance clear. Guards against a slip to
    # imperative ("Corriger…", "Vérifier…") which would break the tone.
    ALLOWED_STARTS = ("J'ai ", "Le ", "Relancer ", "Je n'ai ")
    for rule in UX_RULES:
        for choice in rule["choices"]:
            assert choice["label"].startswith(ALLOWED_STARTS), (
                f"{rule['ux_id']}: unexpected label prefix in {choice['label']!r}"
            )
