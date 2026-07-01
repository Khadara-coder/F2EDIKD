from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.delivery import (
    analyze_delivery_layout,
    extract_delivery_address,
    find_delivery_label,
    is_internal_company_candidate,
    is_street_line,
    purify_delivery_address,
    resolve_delivery_address,
    score_text_delivery_candidate,
)
from app.masterdata import resolve_delivery_with_masterdata, score_partner_service_name, validate_delivery_with_master

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "golden" / "03_layout_delivery"


INTERLEAVED_TEXT = """BON DE COMMANDE
Facture a                    Adresse de livraison
AUTRE CLIENT SA                SOCIETE TEST LIVRAISON
10 RUE PARIS                   18 AVENUE DU PONT DE TASSET
75001 PARIS                    74960 MEYTHET
FRANCE                         FRANCE
"""


@pytest.fixture
def layout_delivery():
    return json.loads((FIXTURES / "layout.json").read_text(encoding="utf-8"))


def test_interleaved_text_marks_low_confidence():
    address = extract_delivery_address(INTERLEAVED_TEXT)
    assert address["Confiance"] == "moyenne"
    assert score_text_delivery_candidate(address) < 80


def test_resolve_prefers_geometry_on_interleaved_side_by_side(layout_delivery):
    resolved = resolve_delivery_address(INTERLEAVED_TEXT, None, layout_delivery)
    assert resolved["Source retenue"] == "geometrie"
    assert resolved["Code postal"] == "74960"
    assert resolved["Ville"] == "MEYTHET"
    assert resolved["Rue"] == "18 AVENUE DU PONT DE TASSET"


def test_layout_rejects_billing_candidate_closer_to_facture_anchor(layout_delivery):
    analysis = analyze_delivery_layout(layout_delivery)
    postals = {item["Code postal"] for item in analysis["address_candidates"]}
    assert "74960" in postals
    assert "75001" not in postals


def test_layout_excludes_bosch_drancy_internal_address():
    layout = {
        "source": "pdf_text",
        "width": 600,
        "height": 800,
        "lines": [
            {"text": "Adresse de livraison", "bbox": {"x0": 40, "y0": 80, "x1": 180, "y1": 95}},
            {"text": "BOSCH PRODUITS FINIS", "bbox": {"x0": 40, "y0": 120, "x1": 190, "y1": 135}},
            {"text": "126 RUE DE STALINGRAD", "bbox": {"x0": 40, "y0": 140, "x1": 210, "y1": 155}},
            {"text": "93700 DRANCY CEDEX", "bbox": {"x0": 40, "y0": 160, "x1": 190, "y1": 175}},
            {"text": "Adresse de livraison", "bbox": {"x0": 330, "y0": 80, "x1": 480, "y1": 95}},
            {"text": "CLIENT LIVRAISON", "bbox": {"x0": 330, "y0": 120, "x1": 470, "y1": 135}},
            {"text": "18 AVENUE DU PONT", "bbox": {"x0": 330, "y0": 140, "x1": 480, "y1": 155}},
            {"text": "74960 MEYTHET", "bbox": {"x0": 330, "y0": 160, "x1": 430, "y1": 175}},
        ],
    }

    analysis = analyze_delivery_layout(layout)
    postals = {item["Code postal"] for item in analysis["address_candidates"]}

    assert "93700" not in postals
    assert "74960" in postals


def test_layout_builds_delivery_candidate_from_noisy_anchor_and_city_reference(monkeypatch, tmp_path):
    import app.postal_reference as postal_reference

    path = tmp_path / "fr_communes.json"
    path.write_text(
        json.dumps([{"nom": "Mainvilliers", "codesPostaux": ["28300"], "code": "28229"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTAL_REFERENCE_PATH", str(path))
    postal_reference.load_postal_reference.cache_clear()

    layout = {
        "source": "ocr",
        "width": 600,
        "height": 800,
        "lines": [
            {"text": "Fax 126 RUE DE STALINGRAD", "bbox": {"x0": 170, "y0": 190, "x1": 405, "y1": 198}},
            {"text": "JT 93700 DRANCY CX", "bbox": {"x0": 22, "y0": 204, "x1": 377, "y1": 210}},
            {"text": "Port avancé dresse de livraison", "bbox": {"x0": 21, "y0": 238, "x1": 395, "y1": 244}},
            {"text": "Type livraison. Livre GERONDEAU 28", "bbox": {"x0": 21, "y0": 250, "x1": 358, "y1": 257}},
            {"text": "DELAI 22 6 26 ll RUE MAUD FONTENOY - N° de compte :15016224", "bbox": {"x0": 21, "y0": 257, "x1": 507, "y1": 272}},
            {"text": "Société ....... GERONDEAU MAINVILLIERS Sanitaire -", "bbox": {"x0": 21, "y0": 272, "x1": 252, "y1": 279}},
        ],
    }

    analysis = analyze_delivery_layout(layout)
    candidate = analysis["address_candidates"][0]

    assert candidate["Code postal"] == "28300"
    assert candidate["Ville"] == "MAINVILLIERS"
    assert candidate["Rue"] == "11 RUE MAUD FONTENOY"
    assert candidate["Source candidat"] == "ancre_livraison"
    assert candidate["Score geometrie"] >= 70


def test_layout_duplicate_header_address_does_not_hide_delivery_candidate(monkeypatch, tmp_path):
    import app.postal_reference as postal_reference

    path = tmp_path / "fr_communes.json"
    path.write_text(
        json.dumps([{"nom": "Chambray-lès-Tours", "codesPostaux": ["37170"], "code": "37050"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTAL_REFERENCE_PATH", str(path))
    postal_reference.load_postal_reference.cache_clear()

    layout = {
        "source": "pdf_text",
        "width": 600,
        "height": 800,
        "lines": [
            {"text": "GARANKA HOLDING", "bbox": {"x0": 23, "y0": 37, "x1": 170, "y1": 50}},
            {"text": "42 RUE MICHAEL FARADAY", "bbox": {"x0": 23, "y0": 58, "x1": 171, "y1": 70}},
            {"text": "37170 CHAMBRAY LES TOURS", "bbox": {"x0": 23, "y0": 86, "x1": 182, "y1": 98}},
            {"text": "93711 DRANCY", "bbox": {"x0": 343, "y0": 237, "x1": 408, "y1": 248}},
            {"text": "Adresse de Livraison", "bbox": {"x0": 31, "y0": 266, "x1": 122, "y1": 276}},
            {"text": "GARANKA HOLDING", "bbox": {"x0": 31, "y0": 276, "x1": 148, "y1": 286}},
            {"text": "42 RUE MICHAEL FARADAY", "bbox": {"x0": 31, "y0": 287, "x1": 148, "y1": 297}},
            {"text": "37170 CHAMBRAY LES TOURS", "bbox": {"x0": 31, "y0": 298, "x1": 162, "y1": 308}},
        ],
    }

    resolved = resolve_delivery_address("", "A2601724.pdf", layout, analyze_delivery_layout(layout))

    assert resolved["Source retenue"] == "geometrie"
    assert resolved["Code postal"] == "37170"
    assert resolved["Ville"] == "CHAMBRAY LES TOURS"
    assert resolved["Rue"] == "42 RUE MICHAEL FARADAY"


def test_layout_ignores_generic_delivery_instruction_anchor(monkeypatch, tmp_path):
    import app.postal_reference as postal_reference

    path = tmp_path / "fr_communes.json"
    path.write_text(
        json.dumps(
            [
                {"nom": "Craponne", "codesPostaux": ["69290"], "code": "69069"},
                {"nom": "Lyon", "codesPostaux": ["69007"], "code": "69123"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTAL_REFERENCE_PATH", str(path))
    postal_reference.load_postal_reference.cache_clear()

    layout = {
        "source": "pdf_text",
        "width": 600,
        "height": 900,
        "lines": [
            {
                "text": "de nos agences a livrer a une seule adresse, veuillez imperativement",
                "bbox": {"x0": 25, "y0": 747, "x1": 496, "y1": 757},
            },
            {"text": "590 Avenue Pierre Auguste Roiret", "bbox": {"x0": 25, "y0": 767, "x1": 260, "y1": 777}},
            {"text": "69290 CRAPONNE", "bbox": {"x0": 25, "y0": 787, "x1": 180, "y1": 797}},
            {"text": "A livrer a l'adresse ci-dessous :", "bbox": {"x0": 59, "y0": 382, "x1": 250, "y1": 392}},
            {"text": "PPC", "bbox": {"x0": 59, "y0": 405, "x1": 90, "y1": 415}},
            {"text": "28 rue Croix Barret", "bbox": {"x0": 59, "y0": 421, "x1": 198, "y1": 431}},
            {"text": "69007 LYON", "bbox": {"x0": 59, "y0": 437, "x1": 150, "y1": 447}},
        ],
    }

    resolved = resolve_delivery_address("", "CDEFRS.pdf", layout, analyze_delivery_layout(layout))

    assert resolved["Code postal"] == "69007"
    assert resolved["Ville"] == "LYON"
    assert resolved["Rue"] == "28 rue Croix Barret"


def test_layout_uses_city_reference_to_ignore_wrong_drancy_fragment(monkeypatch, tmp_path):
    import app.postal_reference as postal_reference

    path = tmp_path / "fr_communes.json"
    path.write_text(
        json.dumps(
            [
                {"nom": "Drancy", "codesPostaux": ["93700"], "code": "93029"},
                {"nom": "Six-Fours-les-Plages", "codesPostaux": ["83140"], "code": "83129"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTAL_REFERENCE_PATH", str(path))
    postal_reference.load_postal_reference.cache_clear()

    layout = {
        "source": "ocr",
        "width": 600,
        "height": 800,
        "lines": [
            {"text": "DESTINATAIRE 126 RUE DE STALINGRAD", "bbox": {"x0": 41, "y0": 167, "x1": 416, "y1": 182}},
            {"text": "LIVRAISON Zone Des Negadoux 3700 DRANCY", "bbox": {"x0": 37, "y0": 178, "x1": 389, "y1": 192}},
            {"text": "83140 SIX FOURS LES PLAGES Tel: 08 20003000", "bbox": {"x0": 92, "y0": 192, "x1": 449, "y1": 198}},
        ],
    }

    analysis = analyze_delivery_layout(layout)
    candidate = analysis["address_candidates"][0]

    assert candidate["Code postal"] == "83140"
    assert candidate["Ville"] == "SIX FOURS LES PLAGES"
    assert candidate["Rue"] == "Zone Des Negadoux"
    assert "DRANCY" not in (candidate.get("Nom / service") or "")
    assert "DRANCY" not in candidate["Adresse complete"]


def test_purifies_delivery_address_to_real_address_only():
    candidate = {
        "Adresse complete": "\n".join(
            [
                "A livrer a l'adresse ci-dessous :",
                "PPC",
                "28 rue Croix Barret",
                "69007 LYON",
                "FRANCE",
                "colisages separes a identifier",
            ]
        ),
        "Nom / service": "A livrer a l'adresse ci-dessous : / PPC",
        "Rue": "28 rue Croix Barret",
        "Code postal": "69007",
        "Ville": "LYON",
        "Pays": "FRANCE",
    }

    purify_delivery_address(candidate)

    assert candidate["Adresse complete"] == "PPC\n28 rue Croix Barret\n69007 LYON\nFRANCE"
    assert candidate["Nom / service"] == "PPC"
    assert candidate["Adresse nettoyee"] == "oui"


def test_text_picks_postal_closer_to_delivery_vocabulary():
    text = """Facture a                    Adresse de livraison
10 RUE PARIS                   18 AV TASSET
75001 PARIS                    74960 MEYTHET
"""
    address = extract_delivery_address(text)
    assert address["Code postal"] == "74960"
    assert address["Ville"] == "MEYTHET"


def test_text_excludes_elm_leblanc_drancy_internal_address():
    text = """BON DE COMMANDE
Adresse de livraison
9034 ELM LEBLANC
126 RUE DE STALINGRAD
93700 DRANCY
CLIENT LIVRAISON
18 AVENUE DU PONT DE TASSET
74960 MEYTHET
FRANCE
"""

    address = extract_delivery_address(text)

    assert address["Code postal"] == "74960"
    assert address["Ville"] == "MEYTHET"
    assert "STALINGRAD" not in (address.get("Rue") or "")


def test_organization_reference_line_is_not_street():
    assert not is_street_line("9034 ELM LEBLANC")
    assert is_street_line("205, Av General Pruneau")
    assert is_street_line("205, Av. General Pruneau")
    assert is_street_line("10 bd Haussmann")
    assert is_street_line("12 rte de Paris")
    assert is_street_line("3 imp. du Moulin")


def test_street_abbreviation_matching_in_masterdata():
    from app.masterdata import street_similarity

    assert street_similarity("205 Av General Pruneau", "205 AVENUE DU GENERAL PRUNEAU") >= 0.88
    assert street_similarity("10 bd Haussmann", "10 BOULEVARD HAUSSMANN") >= 0.88


def test_multiline_lieu_de_livraison_anchor():
    lines = ["LIEU DE", "LIVRAISON", "ANCONETTI", "205, Av General Pruneau", "83000 Toulon"]
    assert find_delivery_label(lines) == (0, 2)


def test_salica_bondecommande_text_extracts_toulon_delivery():
    text = """LIEU DE
LIVRAISON
ANCONETTI
Depot ANC. TOULON
205, Av General Pruneau
83000 Toulon
DESTINATAIRE
FACTURE
A
EXPEDIER
9034 ELM LEBLANC
126 RUE DE STALINGRAD
93700 DRANCY
SALICA
Depot de: ANC. TOULON
2,Rue Diderot - BP 1173
06003 Nice CEDEX 1
QUANTITES
DESIGNATION
"""
    address = extract_delivery_address(text, "BondecommandeFrs.pdf")

    assert address["Code postal"] == "83000"
    assert address["Ville"].upper() == "TOULON"
    assert "PRUNEAU" in (address.get("Rue") or "").upper()
    assert "STALINGRAD" not in (address.get("Rue") or "").upper()


def test_salica_bondecommande_layout_prefers_toulon(monkeypatch, tmp_path):
    import app.postal_reference as postal_reference

    path = tmp_path / "fr_communes.json"
    path.write_text(
        json.dumps(
            [
                {"nom": "Toulon", "codesPostaux": ["83000"], "code": "83137"},
                {"nom": "Nice", "codesPostaux": ["06000", "06003"], "code": "06088"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTAL_REFERENCE_PATH", str(path))
    postal_reference.load_postal_reference.cache_clear()

    layout = {
        "source": "pdf_text",
        "width": 600,
        "height": 850,
        "lines": [
            {"text": "205 Av Du General Pruneau", "bbox": {"x0": 73, "y0": 91, "x1": 250, "y1": 105}},
            {"text": "83000 TOULON", "bbox": {"x0": 94, "y0": 105, "x1": 180, "y1": 117}},
            {"text": "9034 ELM LEBLANC", "bbox": {"x0": 358, "y0": 139, "x1": 470, "y1": 151}},
            {"text": "ANCONETTI", "bbox": {"x0": 82, "y0": 150, "x1": 160, "y1": 162}},
            {"text": "LIEU DE", "bbox": {"x0": 27, "y0": 162, "x1": 80, "y1": 172}},
            {"text": "Depot ANC. TOULON", "bbox": {"x0": 82, "y0": 162, "x1": 210, "y1": 172}},
            {"text": "DESTINATAIRE", "bbox": {"x0": 290, "y0": 162, "x1": 380, "y1": 172}},
            {"text": "126 RUE DE STALINGRAD", "bbox": {"x0": 358, "y0": 162, "x1": 520, "y1": 172}},
            {"text": "LIVRAISON", "bbox": {"x0": 23, "y0": 173, "x1": 90, "y1": 181}},
            {"text": "205, Av General Pruneau", "bbox": {"x0": 82, "y0": 173, "x1": 250, "y1": 181}},
            {"text": "93700 DRANCY", "bbox": {"x0": 358, "y0": 173, "x1": 450, "y1": 181}},
            {"text": "83000 Toulon", "bbox": {"x0": 82, "y0": 184, "x1": 180, "y1": 192}},
            {"text": "FACTURE", "bbox": {"x0": 299, "y0": 236, "x1": 360, "y1": 246}},
            {"text": "EXPEDIER", "bbox": {"x0": 298, "y0": 258, "x1": 360, "y1": 268}},
            {"text": "2,Rue Diderot - BP 1173", "bbox": {"x0": 358, "y0": 258, "x1": 520, "y1": 268}},
            {"text": "06003 Nice CEDEX 1", "bbox": {"x0": 358, "y0": 270, "x1": 480, "y1": 280}},
        ],
    }

    resolved = resolve_delivery_address("", "BondecommandeFrs.pdf", layout, analyze_delivery_layout(layout))

    assert resolved["Code postal"] == "83000"
    assert resolved["Ville"] == "TOULON"
    assert "PRUNEAU" in (resolved.get("Rue") or "").upper()
    assert resolved.get("Source retenue") == "geometrie"


def test_resolve_keeps_clean_text_when_no_layout():
    text = (FIXTURES / "input.txt").read_text(encoding="utf-8")
    resolved = resolve_delivery_address(text, None, None)
    assert resolved["Source retenue"] == "texte"
    assert resolved["Code postal"] == "74960"


def test_service_name_boosts_shipto_score():
    partner = {"name": ".IZI CONFORT CLERMONT", "postal": "63360", "city": "GERZAT", "street": "1 RUE JACQUES MONOD"}
    delivery = {"Nom / service": "IZI CONFORT CLERMONT", "Code postal": "63360", "Ville": "GERZAT"}
    score, reasons = score_partner_service_name(partner, delivery)
    assert score >= 40
    assert "service_name" in reasons


def test_prolians_layout_picks_50180_not_order_reference():
    layout = json.loads(
        (Path(__file__).parent / "fixtures" / "golden" / "05_prolians_delivery" / "layout.json").read_text(
            encoding="utf-8"
        )
    )
    analysis = analyze_delivery_layout(layout)
    postals = [item["Code postal"] for item in analysis["address_candidates"]]
    assert "50180" in postals
    assert "70478" not in postals
    assert analysis["address_candidates"][0]["Code postal"] == "50180"


def test_prolians_text_extracts_delivery_block():
    text = (Path(__file__).parent / "fixtures" / "golden" / "05_prolians_delivery" / "input.txt").read_text(
        encoding="utf-8"
    )
    address = extract_delivery_address(text)
    assert address["Statut"] == "Detectee"
    assert address["Code postal"] == "50180"
    assert address["Ville"] == "AGNEAUX"
    assert "1522 ROUTE DE PERIERS" in (address.get("Rue") or "")


def test_prolians_resolve_with_layout():
    fixture_dir = Path(__file__).parent / "fixtures" / "golden" / "05_prolians_delivery"
    text = (fixture_dir / "input.txt").read_text(encoding="utf-8")
    layout = json.loads((fixture_dir / "layout.json").read_text(encoding="utf-8"))
    resolved = resolve_delivery_address(text, "psp571536_prolians.pdf", layout)
    assert resolved["Code postal"] == "50180"
    assert resolved["Ville"] == "AGNEAUX"


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "psp571536_1qcqzay7025 (6).pdf").exists(),
    reason="PDF de cas reel absent",
)
def test_prolians_real_pdf_delivery():
    import os
    from unittest.mock import MagicMock

    pdf_path = Path(__file__).resolve().parents[1] / "psp571536_1qcqzay7025 (6).pdf"
    for name in ("torch", "transformers"):
        if name not in sys.modules:
            sys.modules[name] = MagicMock()

    os.environ.setdefault("MASTER_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data" / "masterdata"))
    from app.server import pdf_pages_to_text

    payload = pdf_path.read_bytes()
    page = pdf_pages_to_text(payload, "1")[0]
    resolved = resolve_delivery_address(page["text"], pdf_path.name, page.get("layout"))
    assert resolved.get("Code postal") == "50180"
    assert resolved.get("Ville") == "AGNEAUX"


def test_izi_confort_order_validates_shipto():
    import os

    os.environ.setdefault("MASTER_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data" / "masterdata"))
    import app.masterdata as md

    md.master_data_cache = None
    md.master_data_cache_fingerprint = None
    text = (Path(__file__).parent / "fixtures" / "golden" / "01_izi_confort_order" / "input.txt").read_text(
        encoding="utf-8"
    )
    delivery = resolve_delivery_address(text, None, None)
    result = validate_delivery_with_master(
        text,
        {"vat_numbers": ["FR46444768550"]},
        None,
        delivery,
        None,
        order_number="CM-00302553",
    )
    assert result["Statut"] == "Validee master data"
    assert result["SHIPTO"] == "15020046"
    assert result["SOLDTO"] == "15020720"


def test_izi_confort_guided_pipeline_validates_shipto():
    import os

    os.environ["ENABLE_ADDRESS_EMBEDDINGS"] = "false"
    os.environ.setdefault("MASTER_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data" / "masterdata"))
    import app.address_similarity as sim
    import app.masterdata as md

    sim._model_state["loaded"] = False
    sim._model_state["model"] = None
    sim._model_state["error"] = ""
    md.master_data_cache = None
    md.master_data_cache_fingerprint = None

    text = (Path(__file__).parent / "fixtures" / "golden" / "01_izi_confort_order" / "input.txt").read_text(
        encoding="utf-8"
    )
    detected, validated = resolve_delivery_with_masterdata(
        text,
        {"vat_numbers": ["FR46444768550"]},
        None,
        None,
        None,
        order_number="CM-00302553",
    )
    assert detected["Code postal"] == "63360"
    assert validated["Statut"] == "Validee master data"
    assert validated["SHIPTO"] == "15020046"
    assert validated["Guidage masterdata"] == "oui"


def test_prolians_guided_pipeline_detects_50180_without_shipto_match():
    import os

    os.environ["ENABLE_ADDRESS_EMBEDDINGS"] = "false"
    os.environ.setdefault("MASTER_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data" / "masterdata"))
    import app.address_similarity as sim
    import app.masterdata as md

    sim._model_state["loaded"] = False
    sim._model_state["model"] = None
    sim._model_state["error"] = ""
    md.master_data_cache = None
    md.master_data_cache_fingerprint = None

    fixture_dir = Path(__file__).parent / "fixtures" / "golden" / "05_prolians_delivery"
    text = (fixture_dir / "input.txt").read_text(encoding="utf-8")
    layout = json.loads((fixture_dir / "layout.json").read_text(encoding="utf-8"))
    detected, validated = resolve_delivery_with_masterdata(
        text,
        {"vat_numbers": ["FR89542097944"]},
        "psp571536_prolians.pdf",
        layout,
        None,
        order_number="ST 0 CSP 70478",
    )
    assert detected["Code postal"] == "50180"
    assert detected["Ville"] == "AGNEAUX"
    assert validated.get("Guidage masterdata") == "oui"
    assert validated["Statut"] == "Validee master data"
    assert validated.get("Strategie matching") == "adresse_soldto_facturation"
    assert validated.get("Livraison egale facturation SOLDTO") == "oui"
    assert not validated.get("SHIPTO")


def test_extract_delivery_address_spaced_postal(monkeypatch, tmp_path):
    import app.postal_reference as postal_reference

    path = tmp_path / "fr_communes.json"
    path.write_text(
        json.dumps([{"nom": "Ascain", "codesPostaux": ["64310"], "code": "64065"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTAL_REFERENCE_PATH", str(path))
    postal_reference.load_postal_reference.cache_clear()

    text = """BON DE COMMANDE
Adresse de livraison
IZI confort Saint-Jean-de-Luz
ZA Lanzelai - BAT A
64 310 ASCAIN
FRANCE
"""
    address = extract_delivery_address(text)
    assert address["Code postal"] == "64310"
    assert address["Ville"] == "ASCAIN"


def test_layout_rejects_devise_false_postal(monkeypatch, tmp_path):
    import app.postal_reference as postal_reference

    path = tmp_path / "fr_communes.json"
    path.write_text(
        json.dumps(
            [
                {"nom": "Dijon", "codesPostaux": ["21000"], "code": "21231"},
                {"nom": "Corbie", "codesPostaux": ["80200"], "code": "80212"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTAL_REFERENCE_PATH", str(path))
    postal_reference.load_postal_reference.cache_clear()

    layout = {
        "source": "ocr",
        "width": 600,
        "height": 800,
        "lines": [
            {"text": "Adresse de livraison", "bbox": {"x0": 40, "y0": 200, "x1": 180, "y1": 215}},
            {"text": "VERNEY SA", "bbox": {"x0": 40, "y0": 220, "x1": 120, "y1": 235}},
            {"text": "28 RUE DE MAYENCE ZAE CAPNORD", "bbox": {"x0": 40, "y0": 240, "x1": 280, "y1": 255}},
            {"text": "21076 DIJON CEDEX", "bbox": {"x0": 40, "y0": 260, "x1": 180, "y1": 275}},
            {"text": "Devise 80200", "bbox": {"x0": 300, "y0": 400, "x1": 400, "y1": 415}},
        ],
    }

    analysis = analyze_delivery_layout(layout)
    postals = {item["Code postal"] for item in analysis["address_candidates"]}
    assert "21076" in postals or "21000" in postals
    assert "80200" not in postals
    resolved = resolve_delivery_address("", "CF000337886.pdf", layout, analysis)
    assert resolved.get("Code postal") in {"21076", "21000"}
    assert "DEVISE" not in (resolved.get("Ville") or "").upper()


VERNEY_OCR_TEXT = """VI NERNEY. S.A.
28, rue de Mayence - ZAË Capnord 3 rue Daguerre ZA. Broîtes - Rue Chevrier
8.P. 77605 -21076 DIJON CEDEX 21300 CHENOVE BROTTES - 52000 CHAUMONT
N° CF 000337886 DATE 23/06/26 PAGE 1 \\ { ELM LEBLANC
35 rue marcel brot
54000 NANCY
Type livraison. Livre Adresse de livraison
VERNEY SA
Dépot .. + Dijon 28, RUE DE MAYENCE ZAE CAPNORD - BP 77605
Devise......... E 21076DIJON CEDEX
Artic] Désignation Quantité
"""


def test_verney_ocr_text_extracts_dijon_cedex(monkeypatch, tmp_path):
    import app.postal_reference as postal_reference

    path = tmp_path / "fr_communes.json"
    path.write_text(
        json.dumps([{"nom": "Dijon", "codesPostaux": ["21000"], "code": "21231"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTAL_REFERENCE_PATH", str(path))
    postal_reference.load_postal_reference.cache_clear()

    address = extract_delivery_address(VERNEY_OCR_TEXT, "CF000337886 (2).PDF")

    assert address["Code postal"] == "21076"
    assert "DIJON" in address["Ville"]
    assert "MAYENCE" in (address.get("Rue") or "").upper()
    assert "DAGUERRE" not in (address.get("Rue") or "").upper()


def test_internal_company_candidate_matches_stalingrad_without_exact_number():
    candidate = {
        "Code postal": "93700",
        "Ville": "DRANCY",
        "Rue": "124 RUE DE STALINGRAD",
    }
    assert is_internal_company_candidate(candidate) is True
