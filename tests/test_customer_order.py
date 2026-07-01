from __future__ import annotations

from app.engines.customer_order import CustomerOrderNumberEngine, clean_order_candidate


def test_clean_order_candidate_stops_at_page_context():
    assert clean_order_candidate("660093502 Page 1 sur 1 Le 17/06/26") == "660093502"


def test_customer_order_engine_extracts_labeled_number_without_masterdata_hit():
    text = "COMMANDE N° 660093502 Page 1 sur 1\nLe: 17/06/26"

    result = CustomerOrderNumberEngine().extract(text)

    assert result["engine"] == "customer_order_number"
    assert result["order_number"] == "660093502"
    assert result["candidates"][0]["value"] == "660093502"
