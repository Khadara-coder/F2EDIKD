from app.document import build_cross_validation


def test_cross_validation_coherent():
    result = build_cross_validation(
        {"Statut": "Confirmee master data", "KUNNR": "15020720"},
        {"Statut": "Validee master data", "SOLDTO": "15020720"},
    )
    assert result["Statut"] == "Coherent"


def test_cross_validation_conflict():
    result = build_cross_validation(
        {"Statut": "Confirmee master data", "KUNNR": "15020720"},
        {"Statut": "Validee master data", "SOLDTO": "99999999"},
    )
    assert result["Statut"] == "Conflit commande/client"
