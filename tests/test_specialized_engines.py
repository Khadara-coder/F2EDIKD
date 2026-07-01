from __future__ import annotations

import json
from pathlib import Path

from app.engines.delivery_address import DeliveryAddressEngine
from app.engines.order_lines import OrderLinesEngine
from app.engines.purchase_order import PurchaseOrderEngine
from app.engines.shipto_matching import ShipToMatchingEngine
from app.engines.tax_identification import TaxIdentificationEngine


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "golden"


def test_delivery_address_engine_detects_layout_address():
    fixture_dir = FIXTURES / "03_layout_delivery"
    text = (fixture_dir / "input.txt").read_text(encoding="utf-8")
    layout = json.loads((fixture_dir / "layout.json").read_text(encoding="utf-8"))

    result = DeliveryAddressEngine().detect(text, layout=layout)

    assert result["engine"] == "delivery_address"
    assert result["address"]["Code postal"] == "74960"
    assert result["address"]["Ville"] == "MEYTHET"
    assert result["layout_analysis"]["address_candidates"]


def test_shipto_matching_engine_matches_from_detected_address(monkeypatch):
    monkeypatch.setenv("ENABLE_ADDRESS_EMBEDDINGS", "false")
    fixture_dir = FIXTURES / "01_izi_confort_order"
    text = (fixture_dir / "input.txt").read_text(encoding="utf-8")
    delivery = DeliveryAddressEngine().detect(text)["address"]

    result = ShipToMatchingEngine().match(
        text=text,
        fields={"vat_numbers": ["FR46444768550"]},
        delivery_address=delivery,
        order_number="CM-00302553",
    )

    assert result["engine"] == "shipto_matching"
    assert result["shipto"]["Statut"] == "Validee master data"
    assert result["shipto"]["SHIPTO"] == "15020046"


def test_order_lines_engine_extracts_rows():
    text = "\n".join(
        [
            "Code article Designation Quantite Prix unitaire Montant",
            "123456789 Widget premium 2 10,00 EUR 20,00 EUR",
            "Total HT 20,00 EUR",
        ]
    )

    result = OrderLinesEngine().extract(text, materials_by_id={})

    assert result["engine"] == "order_lines"
    assert result["lines"][0]["article"] == "123456789"


def test_tax_identification_engine_filters_invalid_vat():
    result = TaxIdentificationEngine().extract("TVA FR48 2004 1010 1602 SIREN 200 410 101")

    assert result["engine"] == "tax_identification"
    assert result["vat_numbers"] == []
    assert result["expected_vat_from_siren"] == ["FR65200410101"]


def test_purchase_order_engine_orchestrates_specialized_engines(monkeypatch):
    monkeypatch.setenv("ENABLE_ADDRESS_EMBEDDINGS", "false")
    fixture_dir = FIXTURES / "01_izi_confort_order"
    text = (fixture_dir / "input.txt").read_text(encoding="utf-8")

    result = PurchaseOrderEngine().run(
        text=text,
        fields={"vat_numbers": ["FR46444768550"]},
        order_number="CM-00302553",
    )

    assert result["engine"] == "purchase_order"
    assert result["delivery"]["engine"] == "delivery_address"
    assert result["tax_identification"]["engine"] == "tax_identification"
    assert result["shipto"]["engine"] == "shipto_matching"
    assert result["shipto"]["shipto"]["SHIPTO"] == "15020046"
    assert result["line_items"]["engine"] == "order_lines"
