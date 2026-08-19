from app.engines.shipto_scoring import (
    extract_evidence,
    score_candidate,
    streets_contradict,
)


def test_streets_contradict_impasse_vs_rue_same_name():
    detected = {
        "number": "1",
        "stype": "IMPASSE",
        "name": "MARTIN LUTHER KING",
        "raw": "1 IMPASSE MARTIN LUTHER KING",
    }
    assert streets_contradict("24 RUE MARTIN LUTHER KING", detected) is True


def test_streets_do_not_contradict_same_number_and_type():
    detected = {
        "number": "24",
        "stype": "RUE",
        "name": "MARTIN LUTHER KING",
        "raw": "24 RUE MARTIN LUTHER KING",
    }
    assert streets_contradict("24 RUE MARTIN LUTHER KING", detected) is False


def test_score_candidate_applies_street_contradiction_malus():
    text = """
    Date Numero 12/08/26 CH3916
    ELM LEBLANC
    Reference Livraison Adresse de livraison
    DEPOT PRINCIPAL
    1 IMPASSE MARTIN LUTHER KING
    34500 BEZIERS
    """
    evidence = extract_evidence(text)
    scored = score_candidate(
        {
            "id": "15017805",
            "name": ".BAURES",
            "street": "24 RUE MARTIN LUTHER KING",
            "city": "BEZIERS",
            "postal": "34500",
            "country": "FR",
        },
        evidence,
        "34500",
        {"34500"},
    )
    assert any(code.startswith("STREET_CONTRADICTION") for code in scored.reason_codes)
    assert scored.score < 20
