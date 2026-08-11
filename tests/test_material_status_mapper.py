"""Integration tests: Materials Statut rules in order review mapper."""

import pandas as pd
import pytest

from src.file2edi.mapper import engine_to_order_review


def _engine_result(article: str) -> dict:
    return {
        "status": "OK",
        "filename": "order.pdf",
        "pdf_hash": "hash-mat",
        "order": {"po_number": "PO-1", "order_date": "2026-08-04"},
        "customer": {
            "soldto": "15019903",
            "shipto": "15019903",
            "name": "Client Test",
            "confidence": 100,
        },
        "lines": {
            "items": [
                {
                    "code_article": article,
                    "description": "Piece test",
                    "quantite": 1,
                    "prix_unitaire_ht": 10,
                }
            ]
        },
    }


@pytest.fixture()
def materials_cache(monkeypatch):
    from src import masterdata_runtime as mdr

    df = pd.DataFrame(
        [
            {
                "MATNR": "111111",
                "MAKTX": "OK",
                "Statut": "Article disponible",
                "VMSTA": "",
            },
            {
                "MATNR": "222222",
                "MAKTX": "STOP",
                "Statut": "no sale",
                "VMSTA": "92",
            },
            {
                "MATNR": "333333",
                "MAKTX": "OLD",
                "Statut": "444444",
                "VMSTA": "97",
                "Commentaire": "17/05/2023",
            },
            {
                "MATNR": "444444",
                "MAKTX": "NEW",
                "Statut": "Article disponible",
                "VMSTA": "",
            },
            {
                "MATNR": "555555",
                "MAKTX": "CHAIN",
                "Statut": "666666",
                "VMSTA": "97",
                "Commentaire": "01/03/2025",
            },
            {
                "MATNR": "666666",
                "MAKTX": "STOP2",
                "Statut": "no sale",
                "VMSTA": "92",
            },
        ]
    )
    monkeypatch.setitem(mdr.CACHE, "materials", {"df": df, "rows": len(df)})
    return mdr


def test_mapper_no_anomaly_when_article_available(materials_cache):
    review = engine_to_order_review("hash-mat", "upl-1", _engine_result("111111"))
    assert not any(a.get("fieldName") == "boschArticle" for a in review["anomalies"])


def test_mapper_warning_no_sale(materials_cache):
    review = engine_to_order_review("hash-mat", "upl-1", _engine_result("222222"))
    msgs = [a["message"] for a in review["anomalies"]]
    assert any("arrêtée (plus commercialisée)" in m for m in msgs)
    assert review["lines"][0]["status"] == "À vérifier"


def test_mapper_warning_replacement_final_available(materials_cache):
    review = engine_to_order_review("hash-mat", "upl-1", _engine_result("333333"))
    msgs = [a["message"] for a in review["anomalies"]]
    assert any(
        "a été remplacée depuis le 17/05/2023 par 444444" in m for m in msgs
    )
    assert not any("statut référence" in m for m in msgs)


def test_mapper_warning_chain_ends_no_sale(materials_cache):
    review = engine_to_order_review("hash-mat", "upl-1", _engine_result("555555"))
    msgs = [a["message"] for a in review["anomalies"]]
    assert any(
        "a été remplacée depuis le 01/03/2025 par 666666" in m
        and "arrêtée (plus commercialisée)" in m
        for m in msgs
    )


def test_mapper_error_missing_article(materials_cache):
    review = engine_to_order_review("hash-mat", "upl-1", _engine_result("999999999"))
    msgs = [a["message"] for a in review["anomalies"]]
    assert any("absente du référentiel Articles" in m for m in msgs)
    assert any(a.get("severity") == "error" for a in review["anomalies"])
