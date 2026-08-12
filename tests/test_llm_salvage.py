"""Tests for LLM salvage extraction fallback."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.llm_salvage import (
    PARTNER_AUTO_FILL_MIN_SCORE,
    _validate_partners_in_masterdata,
    recover_pdf_text,
    salvage_with_llm,
)


def test_recover_pdf_text_uses_partial_buffer():
    text, method = recover_pdf_text(b"%PDF", partial_text="A" * 40)
    assert method == "partial"
    assert len(text) == 40


def test_validate_partners_requires_masterdata_codes():
    md = {
        "customers_by_id": {"15019903": {"name": "Client A"}},
        "partners_by_soldto": {"15019903": [{"id": "15019904", "name": "Ship A"}]},
    }
    ok = _validate_partners_in_masterdata("15019903", "15019904", md)
    bad = _validate_partners_in_masterdata("15019903", "99999999", md)
    assert ok["both_valid"] is True
    assert bad["both_valid"] is False


@patch("app.llm_salvage.recover_pdf_text", return_value=("x" * 80, "partial"))
@patch("app.masterdata.get_master_data")
@patch("app.engines.llm_orderlines.llm_extract_orderlines")
@patch("app.engines.llm_resolver.llm_resolve")
@patch("app.engines.llm_resolver.llm_extract")
def test_salvage_with_llm_returns_review_required(
    mock_extract,
    mock_resolve,
    mock_lines,
    mock_md,
    _recover,
):
    mock_extract.return_value = {
        "nom_client": "REXEL",
        "numero_commande": "PO-123",
        "date_commande": "2026-08-04",
        "adresse_livraison": {"rue": "1 rue Test", "code_postal": "69000", "ville": "Lyon"},
    }
    mock_lines.return_value = [
        {
            "code_article": "7735500779",
            "description": "Ballon ECS",
            "quantite": 1,
            "prix_unitaire_ht": 10,
            "montant_ligne_ht": 10,
        }
    ]
    mock_resolve.return_value = {
        "resolved": True,
        "soldto": "15019903",
        "shipto": "15019904",
        "confidence": 95,
        "score": PARTNER_AUTO_FILL_MIN_SCORE,
        "path": "llm_name_match",
    }
    mock_md.return_value = {
        "customers_by_id": {"15019903": {"name": "Client A", "street": "Rue A", "postal": "69000", "city": "Lyon"}},
        "partners_by_soldto": {
            "15019903": [{"id": "15019904", "name": "Ship A", "street": "Rue B", "postal": "69001", "city": "Lyon"}]
        },
    }

    result = salvage_with_llm(b"pdf", "order.pdf", original_error="boom", pdf_hash="hash")

    assert result is not None
    assert result["status"] == "OK"
    assert result["salvage"] is True
    assert result["rejection"]["decision"] == "REVIEW_REQUIRED"
    assert result["lines"]["count"] == 1
    assert result["customer"]["soldto"] == "15019903"
    assert result["customer"]["shipto"] == "15019904"


@patch("app.llm_salvage.recover_pdf_text", return_value=("", "none"))
def test_salvage_with_llm_returns_none_without_text(_recover):
    assert salvage_with_llm(b"pdf", "order.pdf") is None
