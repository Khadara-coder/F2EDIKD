"""pytest tests for Phase 1 + Phase 2 extraction improvements."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Module imports
# ---------------------------------------------------------------------------
from app.engines.delivery_date import (
    extract_delivery_date,
    extract_delivery_urgency,
    extract_delivery_info,
)
from app.engines.special_instructions import (
    extract_special_instructions,
    extract_warnings,
)
from app.line_items import (
    _extract_customer_reference,
    _extract_payment_terms,
    extract_line_items_from_text,
)
from app.extraction import _sanitize_order_lines, _extract_qty_from_description


# ---------------------------------------------------------------------------
# 1. DELIVERY DATE ENGINE
# ---------------------------------------------------------------------------
class TestDeliveryDate:
    def test_date_ddmmyyyy(self):
        assert extract_delivery_date("Livraison le 31/12/2026") == "2026-12-31"

    def test_date_dash(self):
        assert extract_delivery_date("Livraison le 15-03-2026") == "2026-03-15"

    def test_date_dot(self):
        assert extract_delivery_date("Date: 01.06.2026") == "2026-06-01"

    def test_urgency_urgent(self):
        assert extract_delivery_urgency("URGENT livraison immédiate") == "URGENT"

    def test_urgency_express(self):
        assert extract_delivery_urgency("Livraison EXPRESS souhaitée") == "EXPRESS"

    def test_no_date_returns_none(self):
        assert extract_delivery_date("Produit standard 5 PCE") is None

    def test_delivery_info_combined(self):
        info = extract_delivery_info("URGENT livraison le 25/07/2026")
        assert info.get("delivery_date") == "2026-07-25"
        assert info.get("urgency") == "URGENT"


# ---------------------------------------------------------------------------
# 2. SPECIAL INSTRUCTIONS ENGINE
# ---------------------------------------------------------------------------
class TestSpecialInstructions:
    def test_note_section(self):
        result = extract_special_instructions("Remarques: livrer avant 17h")
        assert result is not None and len(result) > 0

    def test_fragile(self):
        result = extract_special_instructions("Produit FRAGILE à manipuler avec soin")
        assert result and "FRAGILE" in result

    def test_warning_emoji(self):
        result = extract_warnings("⚠️ Attention URGENT")
        assert result and "⚠️" in result

    def test_warning_important(self):
        result = extract_warnings("IMPORTANT: vérifier adresse")
        assert result and "IMPORTANT" in result

    def test_no_instructions_returns_none(self):
        result = extract_special_instructions("Article 7736901359 quantite 5")
        assert result is None


# ---------------------------------------------------------------------------
# 3. CUSTOMER REFERENCE & PAYMENT TERMS
# ---------------------------------------------------------------------------
class TestReferenceAndPaymentTerms:
    def test_customer_ref_extraction(self):
        ref = _extract_customer_reference("ref client: ABC123")
        assert ref != ""

    def test_payment_terms_net30j(self):
        terms = _extract_payment_terms("Conditions paiement: NET 30J")
        assert terms != ""

    def test_payment_terms_comptant(self):
        terms = _extract_payment_terms("Paiement: COMPTANT")
        assert terms != ""

    def test_no_reference_returns_empty(self):
        ref = _extract_customer_reference("Article 7736901359")
        assert ref == ""


# ---------------------------------------------------------------------------
# 4. QUANTITY VARIANTS
# ---------------------------------------------------------------------------
class TestQuantityVariants:
    def test_qty_from_piece(self):
        assert _extract_qty_from_description("5 PIECE 25,77 128,85") == 5.0

    def test_qty_from_pce(self):
        assert _extract_qty_from_description("3 PCE 100,00") == 3.0

    def test_no_qty_returns_none(self):
        assert _extract_qty_from_description("Pas de quantite ici") is None

    def test_article_window_has_customer_reference_key(self):
        rows = extract_line_items_from_text(
            "2PCE MEGALIS 7736902448 1549,71€/ PCE",
            {"7736902448": "MEGALIS TEST"},
        )
        assert rows, "Expected at least one row"
        assert "customer_reference" in rows[0]

    def test_article_window_has_payment_terms_key(self):
        rows = extract_line_items_from_text(
            "2PCE MEGALIS 7736902448 1549,71€/ PCE",
            {"7736902448": "MEGALIS TEST"},
        )
        assert rows, "Expected at least one row"
        assert "payment_terms" in rows[0]


# ---------------------------------------------------------------------------
# 5. EXTRACTION PIPELINE
# ---------------------------------------------------------------------------
class TestExtractionPipeline:
    def test_sanitize_returns_lines(self):
        lines = [
            {
                "code_article": "7736901359",
                "description": "MEGALIS CONDENSATION 28kW",
                "quantite": 2,
                "prix_unitaire_ht": 500.00,
                "montant_ligne_ht": 1000.00,
            }
        ]
        cleaned = _sanitize_order_lines(lines)
        assert len(cleaned) == 1

    def test_sanitize_has_customer_reference(self):
        lines = [
            {
                "code_article": "7736901359",
                "description": "test",
                "quantite": 2,
                "prix_unitaire_ht": 100.00,
                "montant_ligne_ht": 200.00,
                "customer_reference": "CMD-001",
            }
        ]
        cleaned = _sanitize_order_lines(lines)
        assert "customer_reference" in cleaned[0]

    def test_sanitize_has_payment_terms(self):
        lines = [
            {
                "code_article": "7736901359",
                "description": "test",
                "quantite": 1,
                "prix_unitaire_ht": 100.00,
                "montant_ligne_ht": 100.00,
                "payment_terms": "NET 30J",
            }
        ]
        cleaned = _sanitize_order_lines(lines)
        assert "payment_terms" in cleaned[0]

    def test_sanitize_has_special_instructions(self):
        lines = [
            {
                "code_article": "7736901359",
                "description": "test",
                "quantite": 1,
                "prix_unitaire_ht": 100.00,
                "montant_ligne_ht": 100.00,
            }
        ]
        cleaned = _sanitize_order_lines(lines)
        assert "special_instructions" in cleaned[0]

    def test_sanitize_has_warnings(self):
        lines = [
            {
                "code_article": "7736901359",
                "description": "test",
                "quantite": 1,
                "prix_unitaire_ht": 100.00,
                "montant_ligne_ht": 100.00,
            }
        ]
        cleaned = _sanitize_order_lines(lines)
        assert "warnings" in cleaned[0]

    def test_qty_calc_from_amount_price(self):
        lines = [
            {
                "code_article": "7736504816",
                "description": "KIT ENTRETIEN",
                "quantite": None,
                "prix_unitaire_ht": 275.00,
                "montant_ligne_ht": 5500.00,
            }
        ]
        cleaned = _sanitize_order_lines(lines)
        assert cleaned[0]["quantite"] == 20.0
