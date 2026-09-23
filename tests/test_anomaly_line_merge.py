"""Tests for merging identical per-line anomalies in store._anomalies_to_api.

When multiple MATERIAL_STATUS_INVALID rows carry the same body (only the
"Ligne N :" prefix differs), the API collapses them into one row titled
"Lignes N1, N2, N3 : …" and exposes ``mergedAnomalyIds`` for frontend
fan-out. See ADV request 2026-09-23 (in-conversation clarification).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.file2edi.store import File2EdiStore  # noqa: E402


def _store() -> File2EdiStore:
    return File2EdiStore.__new__(File2EdiStore)


def _mat_anomaly(line: int, body: str = "la référence 7736606771 a été remplacée depuis le 24/06/2026 par 7733703987.", **extra):
    base = {
        "anomalyId": f"an-line-{line}",
        "orderId": "o-1",
        "severity": "warning",
        "fieldName": "MATERIAL_STATUS_INVALID",
        "message": f"Ligne {line} : {body}",
        "status": "Ouverte",
        "createdAt": "2026-09-21T10:00:00Z",
        "suggestedReplacement": "7733703987",
    }
    base.update(extra)
    return base


def test_three_identical_line_anomalies_collapse_into_one_row():
    mapped = [
        _mat_anomaly(2),
        _mat_anomaly(3),
        _mat_anomaly(4),
    ]
    merged = _store()._merge_identical_line_anomalies(mapped)

    assert len(merged) == 1
    row = merged[0]
    assert row["message"] == "Lignes 2, 3, 4 : la référence 7736606771 a été remplacée depuis le 24/06/2026 par 7733703987."
    assert row["mergedAnomalyIds"] == ["an-line-2", "an-line-3", "an-line-4"]
    assert row["mergedLineNumbers"] == [2, 3, 4]


def test_line_numbers_are_sorted_ascending_regardless_of_input_order():
    mapped = [
        _mat_anomaly(5),
        _mat_anomaly(2),
        _mat_anomaly(9),
    ]
    merged = _store()._merge_identical_line_anomalies(mapped)
    assert merged[0]["message"].startswith("Lignes 2, 5, 9 : ")
    assert merged[0]["mergedLineNumbers"] == [2, 5, 9]


def test_anomalies_with_different_bodies_are_not_merged_even_if_same_code():
    mapped = [
        _mat_anomaly(2, body="ref A remplacée par X"),
        _mat_anomaly(3, body="ref B remplacée par Y"),
    ]
    merged = _store()._merge_identical_line_anomalies(mapped)
    assert len(merged) == 2
    assert all("mergedAnomalyIds" not in row for row in merged)


def test_different_suggested_replacements_break_the_merge_group():
    # Same body, different Y → separate rows (different replacement paths).
    mapped = [
        _mat_anomaly(2, suggestedReplacement="AAAA"),
        _mat_anomaly(3, suggestedReplacement="BBBB"),
    ]
    merged = _store()._merge_identical_line_anomalies(mapped)
    assert len(merged) == 2


def test_singleton_line_anomaly_is_not_wrapped_in_a_merge_row():
    mapped = [_mat_anomaly(2)]
    merged = _store()._merge_identical_line_anomalies(mapped)
    assert len(merged) == 1
    assert "mergedAnomalyIds" not in merged[0]
    assert merged[0]["message"].startswith("Ligne 2 : ")


def test_non_line_anomalies_pass_through_unchanged():
    non_line = {
        "anomalyId": "an-header",
        "orderId": "o-1",
        "fieldName": "ORDER_KEY_MISSING",
        "message": "Le numéro de commande client est manquant.",
        "status": "Bloquante",
    }
    mapped = [non_line, _mat_anomaly(2), _mat_anomaly(3)]
    merged = _store()._merge_identical_line_anomalies(mapped)
    # 1 non-line + 1 merged
    assert len(merged) == 2
    assert any(m.get("anomalyId") == "an-header" for m in merged)


def test_merged_status_is_the_worst_case_across_the_group():
    mapped = [
        _mat_anomaly(2, status="Corrigée"),
        _mat_anomaly(3, status="Ouverte"),
        _mat_anomaly(4, status="Corrigée"),
    ]
    merged = _store()._merge_identical_line_anomalies(mapped)
    assert merged[0]["status"] == "Ouverte"

    with_blocking = [
        _mat_anomaly(2, status="Corrigée"),
        _mat_anomaly(3, status="Bloquante"),
    ]
    merged = _store()._merge_identical_line_anomalies(with_blocking)
    assert merged[0]["status"] == "Bloquante"


def test_ux_choice_is_propagated_from_any_sibling_that_already_set_it():
    mapped = [
        _mat_anomaly(2, uxChoice=None),
        _mat_anomaly(3, uxChoice="correct_and_recontrol"),
        _mat_anomaly(4, uxChoice=None),
    ]
    merged = _store()._merge_identical_line_anomalies(mapped)
    assert merged[0]["uxChoice"] == "correct_and_recontrol"


def test_merge_key_is_case_and_whitespace_sensitive_on_the_body():
    # Trailing whitespace or capitalization differences count as different
    # bodies — this is intentional so subtle wording variants stay separate.
    mapped = [
        _mat_anomaly(2, body="Reference remplacée"),
        _mat_anomaly(3, body="reference remplacée"),  # different case
    ]
    merged = _store()._merge_identical_line_anomalies(mapped)
    assert len(merged) == 2


def test_material_status_invalid_is_not_blocking_per_product_decision():
    from src.rejection_catalog import issue_taxonomy

    for code in ("MATERIAL_STATUS_INVALID", "ARTICLE_NOT_FOUND", "NO_VALID_ARTICLE"):
        tax = issue_taxonomy(code)
        assert tax["blocking"] is False, f"{code} must be non-blocking per UX-08 decision"
        assert tax["issue_severity"] == "WARNING", f"{code} must surface as warning, not error"
