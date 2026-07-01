from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("MASTER_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data" / "masterdata"))

from app.masterdata import get_master_data, infer_buyer_from_master, lookup_customer_by_order_number, validate_delivery_with_master
from app.text_utils import norm_order_key


@pytest.fixture(scope="module")
def master_data():
    get_master_data.cache_clear() if hasattr(get_master_data, "cache_clear") else None
    global master_data_cache, master_data_cache_fingerprint
    import app.masterdata as md

    md.master_data_cache = None
    md.master_data_cache_fingerprint = None
    return get_master_data()


def test_master_data_indexes_loaded(master_data):
    assert master_data["loaded"] is True
    assert len(master_data["customers_by_id"]) > 0
    assert len(master_data["customers_by_vat"]) > 0
    assert len(master_data["customers_by_postal"]) > 0
    assert len(master_data["salesorders_by_bstnk"]) > 0


def test_lookup_customer_by_order_number(master_data):
    buyer = lookup_customer_by_order_number(master_data, "CM-00302553")
    assert buyer is not None
    assert buyer["id"] == "15020720"
    assert buyer["_reason"].startswith("bstnk:")


def test_infer_buyer_uses_order_number(master_data):
    buyer = infer_buyer_from_master(
        master_data,
        text="",
        fields={},
        filename=None,
        order_number="CM-00302553",
    )
    assert buyer is not None
    assert buyer["id"] == "15020720"


def test_infer_buyer_vat_narrows_candidates(master_data):
    buyer = infer_buyer_from_master(
        master_data,
        text="IZI CONFORT GERZAT 63360",
        fields={"vat_numbers": ["FR46444768550"]},
        filename=None,
        order_number=None,
    )
    assert buyer is not None
    assert buyer["id"] == "15020720"


def test_validate_order_number(master_data):
    from app.masterdata import validate_order_number

    result = validate_order_number(master_data, "CM-00302553")
    assert result["Statut"] == "Confirmee master data"
    assert result["KUNNR"] == "15020720"
    assert result["Occurrences"] >= 1


def test_validate_order_number_conflict(master_data):
    from app.masterdata import validate_order_number

    result = validate_order_number(master_data, "CM-00302553", soldto_id="99999999")
    assert result["Statut"] == "Conflit SOLDTO"


def test_norm_order_key():
    assert norm_order_key(" cm-00302553 ") == "CM-00302553"


def test_filter_candidates_keeps_primary_detected_address():
    from app.masterdata import filter_candidates_to_primary_detection

    primary = {"Code postal": "69007", "Ville": "LYON", "Score resolution": 100}
    candidates = [
        {"Code postal": "69007", "Ville": "LYON", "Rue": "28 rue Croix Barret"},
        {"Code postal": "69290", "Ville": "CRAPONNE", "Rue": "590 Avenue Pierre Auguste Roiret"},
    ]

    filtered = filter_candidates_to_primary_detection(candidates, primary)

    assert filtered == [candidates[0]]


def test_filter_shipto_candidates_strict_does_not_fallback_to_incompatible_partner():
    from app.masterdata import filter_shipto_candidates

    partners = [
        {"id": "15901207", "postal": "44800", "city": "SAINT-HERBLAIN", "street": "2 RUE DU CHENE LASSE"},
        {"id": "15000001", "postal": "69290", "city": "CRAPONNE", "street": "590 AVENUE PIERRE AUGUSTE ROIRET"},
    ]
    delivery = {"Code postal": "69007", "Ville": "LYON", "Rue": "28 rue Croix Barret"}

    assert filter_shipto_candidates(partners, delivery, allow_fallback=False) == []


def test_score_shipto_ignores_service_name_when_precise_address_exists():
    from app.masterdata import score_shipto

    partner = {
        "id": "1",
        "name": "PLATEFORME LOGISTIQUE CCL",
        "postal": "75001",
        "city": "PARIS",
        "street": "1 RUE DE PARIS",
        "country": "FR",
    }
    delivery = {
        "Nom / service": "PLATEFORME LOGISTIQUE CCL",
        "Rue": "8 CHEMIN DE NAUDINATS",
        "Code postal": "31770",
        "Ville": "COLOMIERS",
    }

    score, reasons, _layout = score_shipto(partner, delivery, None)

    assert score == 0
    assert "service_name" not in reasons


def test_infer_buyer_from_delivery_shipto_address():
    from app.masterdata import infer_buyer_from_master

    data = {
        "customers_by_id": {
            "15022025": {
                "id": "15022025",
                "name": "COMPTOIR COMMERCIAL DU LANGUEDOC S.",
                "postal": "81104",
                "city": "CASTRES CEDEX",
                "street": "CHEMIN DE MONTREVEIL",
                "vat": "FR07716320619",
            },
            "15019226": {
                "id": "15019226",
                "name": ".CCL",
                "postal": "31770",
                "city": "COLOMIERS",
                "street": "8 CHEMIN DES NAUDINATS",
                "vat": "FR07716320619",
            },
        },
        "customers": [],
        "customers_by_vat": {},
        "customers_by_postal": {
            "31770": [
                {
                    "id": "15019226",
                    "name": ".CCL",
                    "postal": "31770",
                    "city": "COLOMIERS",
                    "street": "8 CHEMIN DES NAUDINATS",
                    "vat": "FR07716320619",
                }
            ]
        },
        "partners_by_postal": {
            "31770": [
                (
                    "15022025",
                    {
                        "id": "15019226",
                        "name": ".CCL",
                        "postal": "31770",
                        "city": "COLOMIERS",
                        "street": "8 CHEMIN DES NAUDINATS",
                        "country": "FR",
                    },
                )
            ]
        },
        "partners_by_soldto": {
            "15022025": [
                {
                    "id": "15019226",
                    "name": ".CCL",
                    "postal": "31770",
                    "city": "COLOMIERS",
                    "street": "8 CHEMIN DES NAUDINATS",
                    "country": "FR",
                }
            ]
        },
        "salesorders_by_bstnk": {},
    }
    delivery = {
        "Nom / service": "PLATEFORME LOGISTIQUE CCL",
        "Rue": "8 CHEMIN DE NAUDINATS",
        "Code postal": "31770",
        "Ville": "COLOMIERS",
    }

    buyer = infer_buyer_from_master(data, "", {"vat_numbers": []}, None, None, delivery)

    assert buyer is not None
    assert buyer["id"] == "15022025"
    assert "delivery_shipto:15019226" in buyer["_reason"]


def test_direct_shipto_address_match_can_be_tiebroken_by_vat_soldto():
    from app.masterdata import direct_shipto_matches_by_address, prefer_shipto_matches_with_soldto_filter

    data = {
        "partners_by_postal": {
            "31770": [
                (
                    "99999999",
                    {
                        "id": "99900001",
                        "name": ".AUTRE",
                        "postal": "31770",
                        "city": "COLOMIERS",
                        "street": "8 CHEMIN DES NAUDINATS",
                    },
                ),
                (
                    "15022025",
                    {
                        "id": "15019226",
                        "name": ".CCL",
                        "postal": "31770",
                        "city": "COLOMIERS",
                        "street": "8 CHEMIN DES NAUDINATS",
                    },
                ),
            ]
        }
    }
    delivery = {
        "Rue": "8 CHEMIN DE NAUDINATS",
        "Code postal": "31770",
        "Ville": "COLOMIERS",
    }

    matches = direct_shipto_matches_by_address(data, delivery)
    matches, filtered = prefer_shipto_matches_with_soldto_filter(matches, {"15022025"})

    assert filtered is True
    assert matches[0][2] == "15022025"
    assert matches[0][3]["id"] == "15019226"


def test_direct_shipto_address_match_keeps_better_address_over_vat_filter():
    from app.masterdata import direct_shipto_matches_by_address, prefer_shipto_matches_with_soldto_filter

    data = {
        "partners_by_postal": {
            "31770": [
                (
                    "15022025",
                    {
                        "id": "15019226",
                        "name": ".CCL",
                        "postal": "31770",
                        "city": "COLOMIERS",
                        "street": "8 CHEMIN DES NAUDINATS",
                    },
                ),
                (
                    "99999999",
                    {
                        "id": "99900001",
                        "name": ".AUTRE",
                        "postal": "31770",
                        "city": "COLOMIERS",
                        "street": "8 CHEMIN DE LA CHASSE",
                    },
                ),
            ]
        }
    }
    delivery = {
        "Rue": "8 CHEMIN DE NAUDINATS",
        "Code postal": "31770",
        "Ville": "COLOMIERS",
    }

    matches = direct_shipto_matches_by_address(data, delivery)
    matches, filtered = prefer_shipto_matches_with_soldto_filter(matches, {"99999999"})

    assert filtered is False
    assert matches[0][2] == "15022025"
    assert matches[0][3]["id"] == "15019226"


def test_soldto_billing_match_when_no_shipto_partner():
    from app.masterdata import soldto_billing_matches_by_address

    data = {
        "customers": [
            {
                "id": "15017119",
                "name": "GARANKA HOLDING TOURS",
                "postal": "37170",
                "city": "CHAMBRAY-LES-TOURS",
                "street": "42 RUE MICHAEL FARADAY",
                "country": "FR",
                "vat": "FR19504035056",
            },
            {
                "id": "15015743",
                "name": "PARTEDIS CHAUFFAGE SANITAIRE",
                "postal": "37170",
                "city": "CHAMBRAY-LES-TOURS",
                "street": "8 RUE JEAN PERRIN",
                "country": "FR",
                "vat": "FR57467200515",
            },
        ],
        "customers_by_postal": {
            "37170": [
                {
                    "id": "15017119",
                    "name": "GARANKA HOLDING TOURS",
                    "postal": "37170",
                    "city": "CHAMBRAY-LES-TOURS",
                    "street": "42 RUE MICHAEL FARADAY",
                    "country": "FR",
                    "vat": "FR19504035056",
                },
                {
                    "id": "15015743",
                    "name": "PARTEDIS CHAUFFAGE SANITAIRE",
                    "postal": "37170",
                    "city": "CHAMBRAY-LES-TOURS",
                    "street": "8 RUE JEAN PERRIN",
                    "country": "FR",
                    "vat": "FR57467200515",
                },
            ]
        },
    }
    delivery = {
        "Rue": "42 RUE MICHAEL FARADAY",
        "Code postal": "37170",
        "Ville": "CHAMBRAY LES TOURS",
    }

    matches = soldto_billing_matches_by_address(data, delivery)

    assert matches
    assert matches[0][2] == "15017119"
    assert all(match[2] != "15015743" for match in matches)


def test_global_shipto_ranking_rejects_wrong_street_at_same_postal():
    from app.masterdata import rank_global_shipto_matches

    data = {
        "partners_by_postal": {
            "37170": [
                (
                    "15015743",
                    {
                        "id": "15005211",
                        "name": ".PARTEDIS CHAUFFAGE SANITAIRE",
                        "postal": "37170",
                        "city": "CHAMBRAY-LES-TOURS",
                        "street": "8 RUE JEAN PERRIN",
                    },
                ),
                (
                    "15022025",
                    {
                        "id": "15019226",
                        "name": ".CCL",
                        "postal": "37170",
                        "city": "COLOMIERS",
                        "street": "8 CHEMIN DES NAUDINATS",
                    },
                ),
            ]
        }
    }
    delivery = {
        "Rue": "42 RUE MICHAEL FARADAY",
        "Code postal": "37170",
        "Ville": "CHAMBRAY LES TOURS",
    }

    results = rank_global_shipto_matches(data, delivery, None, "", None)

    assert results == []


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "A2601623 (2).PDF").exists(),
    reason="PDF cas GARANKA absent",
)
def test_garanka_pdf_matches_soldto_billing_address():
    import os
    from pathlib import Path

    from app.engines.shipto_matching import ShipToMatchingEngine
    from app.pdf_reader import pdf_pages_to_text

    os.environ.setdefault("MASTER_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data" / "masterdata"))
    import app.masterdata as md

    md.master_data_cache = None
    md.master_data_cache_fingerprint = None

    pdf_path = Path(__file__).resolve().parents[1] / "A2601623 (2).PDF"
    page = pdf_pages_to_text(pdf_path.read_bytes(), "1")[0]
    result = ShipToMatchingEngine().resolve_best(
        text=page["text"],
        fields={"vat_numbers": []},
        filename=pdf_path.name,
        layout=page.get("layout"),
    )
    detected = result["detected_address"]
    validated = result["shipto"]

    assert detected.get("Rue") == "42 RUE MICHAEL FARADAY"
    assert detected.get("Code postal") == "37170"
    assert validated.get("SOLDTO") == "15017119"
    assert validated.get("Strategie matching") == "adresse_soldto_facturation"
    assert "JEAN PERRIN" not in (validated.get("Rue") or "")


def test_validate_delivery_with_master_does_not_return_zero_score_shipto():
    delivery = {
        "Rue": "999 AVENUE INCONNUE",
        "Code postal": "99999",
        "Ville": "VILLE INCONNUE",
        "Pays": "FRANCE",
    }

    result = validate_delivery_with_master(
        "",
        {"vat_numbers": []},
        None,
        delivery,
        known_soldto_id="15021754",
    )

    assert result["Statut"] == "SHIPTO non identifie"
    assert result["SOLDTO"] == "15021754"
