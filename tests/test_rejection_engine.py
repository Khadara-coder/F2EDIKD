"""Regression tests for canonical rejection severity decisions."""

from app.engines.rejection_engine import check_rejections
from src.rejection_catalog import normalize_code


def _structured_with_lines(lines):
    return {
        "document": {"Numero de commande": "PO-123", "Type": "commande"},
        "adresses": {
            "Adresse de livraison validee": {
                "SOLDTO": "1000",
                "SHIPTO": "2000",
                "Confiance": 100,
            }
        },
        "lignes_commande": {"lignes": lines},
    }


def test_no_line_items_is_blocking():
    rejections = check_rejections(_structured_with_lines([]))

    rejection = next(item for item in rejections if item["code"] == "NO_LINE_ITEMS")
    assert rejection["severity"] == "blocking"


def test_unknown_article_is_blocking():
    rejections = check_rejections(
        _structured_with_lines(
            [
                {
                    "numero_ligne": 1,
                    "code_article": "UNKNOWN-ARTICLE",
                    "quantite": 1,
                    "prix_unitaire_ht": 10.0,
                }
            ]
        ),
        materials={"KNOWNARTICLE": {"MATNR": "KNOWNARTICLE"}},
    )

    rejection = next(item for item in rejections if item["code"] == "ARTICLE_NOT_FOUND")
    assert rejection["severity"] == "blocking"


def test_quantity_invalid_alias_is_canonical():
    assert normalize_code("QUANTITY_INVALID") == "ARTICLE_QUANTITY_INVALID"


def test_duplicate_po_is_review_warning_not_blocking():
    rejections = check_rejections(
        _structured_with_lines(
            [{
                "numero_ligne": 1,
                "code_article": "KNOWNARTICLE",
                "quantite": 1,
                "prix_unitaire_ht": 10.0,
            }]
        ),
        master_data={
            "salesorders_by_bstnk": {"PO-123": {"VBELN": "500001"}},
            "materials_by_id": {"KNOWNARTICLE": {"MATNR": "KNOWNARTICLE"}},
        },
    )

    rejection = next(item for item in rejections if item["code"] == "PO_NUMBER_DUPLICATE")
    assert rejection["severity"] == "warning"
