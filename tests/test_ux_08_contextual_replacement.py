"""Integration test for the UX-08 contextual replacement choice.

ADV validation truth table (row 12) — 4 choices:
  1. "J'ai remplacé la référence par Y"   (contextual, injected here)
  2. "J'ai corrigé la référence article"  (static, from ux_catalog)
  3. "J'ai renseigné une référence de remplacement"
  4. "J'ai supprimé la ligne concernée"

The contextual choice #1 is not a static entry in ux_catalog; it is added
by store._anomaly_to_api when the anomaly carries a `suggestedReplacement`
value (populated by the mapper from masterdata_runtime.material_status_replacement).
Distinct outcome `apply_suggested_replacement_and_recontrol` lets the biz
log separate "ADV used the suggestion" from "ADV typed a different value".
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.file2edi.store import File2EdiStore  # noqa: E402


def _anomaly(**overrides):
    base = {
        "anomalyId": "an-1",
        "orderId": "o-1",
        "severity": "error",
        "fieldName": "MATERIAL_STATUS_INVALID",
        "message": "Ligne 3 : la référence 7736606771 a été remplacée depuis le 24/06/2026 par 7733703987.",
        "status": "Bloquante",
        "createdAt": "2026-09-21T10:00:00Z",
    }
    base.update(overrides)
    return base


def _serialize(anomaly: dict) -> dict:
    # Call the same private method the review payload builder uses so the
    # test exercises the exact code path the API returns.
    store = File2EdiStore.__new__(File2EdiStore)
    return store._anomaly_to_api(dict(anomaly), mapping={}, order={"orderId": "o-1"})


def test_contextual_replacement_choice_prepended_when_suggested_replacement_is_set():
    mapped = _serialize(_anomaly(suggestedReplacement="7733703987"))

    choices = mapped["uxChoices"]
    assert choices[0] == {
        "label": "J'ai remplacé la référence par 7733703987",
        "outcome": "apply_suggested_replacement_and_recontrol",
    }
    # The three static choices from the catalog still follow.
    assert len(choices) == 4
    assert choices[1]["outcome"] == "correct_and_recontrol"
    assert choices[3]["outcome"] == "delete_line_and_recontrol"


def test_no_contextual_choice_when_suggested_replacement_is_absent():
    mapped = _serialize(_anomaly())  # no suggestedReplacement
    choices = mapped["uxChoices"]
    outcomes = [c["outcome"] for c in choices]
    assert "apply_suggested_replacement_and_recontrol" not in outcomes
    assert len(choices) == 3


def test_no_contextual_choice_when_suggested_replacement_is_empty_string():
    mapped = _serialize(_anomaly(suggestedReplacement="   "))
    choices = mapped["uxChoices"]
    outcomes = [c["outcome"] for c in choices]
    assert "apply_suggested_replacement_and_recontrol" not in outcomes


def test_contextual_choice_is_scoped_to_material_status_invalid_only():
    # Other UX-08 codes (ARTICLE_NOT_FOUND, NO_VALID_ARTICLE) do not have a
    # suggested replacement from the masterdata, so even if the field were
    # accidentally set the contextual button must NOT appear on them.
    for code in ("ARTICLE_NOT_FOUND", "NO_VALID_ARTICLE"):
        mapped = _serialize(_anomaly(fieldName=code, suggestedReplacement="9999999999"))
        outcomes = [c["outcome"] for c in mapped["uxChoices"]]
        assert "apply_suggested_replacement_and_recontrol" not in outcomes, (
            f"contextual choice leaked to {code}"
        )


def test_suggested_replacement_is_exposed_on_the_api_payload():
    mapped = _serialize(_anomaly(suggestedReplacement="7733703987"))
    assert mapped.get("suggestedReplacement") == "7733703987"


def test_contextual_choice_label_interpolates_the_replacement_value():
    for y in ("7733703987", "12345678", "AB-9999"):
        mapped = _serialize(_anomaly(suggestedReplacement=y))
        first = mapped["uxChoices"][0]
        assert first["label"] == f"J'ai remplacé la référence par {y}"
