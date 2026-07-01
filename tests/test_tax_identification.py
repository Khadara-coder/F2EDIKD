from __future__ import annotations

from app.engines.tax_identification import TaxIdentificationEngine, french_vat_from_siren
from app.extraction import extract_candidate_fields


def test_french_vat_from_siren():
    assert french_vat_from_siren("444 768 550") == "FR46444768550"
    assert french_vat_from_siren("542097944") == "FR89542097944"


def test_tax_identification_validates_vat_against_siren():
    text = "SIRET 444 768 550 00014 TVA intracommunautaire FR46 444768550"

    result = TaxIdentificationEngine().extract(text)

    assert result["vat_numbers"] == ["FR46444768550"]
    assert result["valid_siren"] == ["444768550"]
    assert result["rejected_vat_candidates"] == []


def test_tax_identification_rejects_wrong_vat_shape_and_suggests_expected_from_siren():
    text = "TVA intracommunautaire FR48 2004 1010 1602 SIREN 200 410 101"

    result = TaxIdentificationEngine().extract(text)

    assert result["vat_numbers"] == []
    assert result["vat_candidates"] == ["FR48 2004 1010 1602"]
    assert result["rejected_vat_candidates"][0]["reason"] == "format_invalide"
    assert result["expected_vat_from_siren"] == ["FR65200410101"]


def test_candidate_fields_use_validated_vat_only():
    text = "TVA intracommunautaire FR48 2004 1010 1602 SIREN 200 410 101"

    fields = extract_candidate_fields(text, "Extraire TVA")

    assert fields["vat_numbers"] == []
    assert fields["vat_candidates"] == ["FR48 2004 1010 1602"]
    assert fields["structured"]["document"]["TVA intracommunautaire"] is None
    assert fields["structured"]["identifiants"]["TVA attendue depuis SIREN"] == ["FR65200410101"]
