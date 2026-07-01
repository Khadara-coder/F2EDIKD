from __future__ import annotations

import json

import pytest

from app.postal_reference import best_postal_city_in_text, load_postal_reference, validate_postal_city


@pytest.fixture(autouse=True)
def clear_postal_reference_cache():
    load_postal_reference.cache_clear()
    yield
    load_postal_reference.cache_clear()


def test_validate_postal_city_ok(monkeypatch, tmp_path):
    path = tmp_path / "fr_communes.json"
    path.write_text(
        json.dumps([{"nom": "Drancy", "codesPostaux": ["93700"], "code": "93029"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTAL_REFERENCE_PATH", str(path))
    load_postal_reference.cache_clear()

    result = validate_postal_city("93700", "DRANCY")

    assert result["status"] == "ok"
    assert result["match"] is True


def test_validate_postal_city_accepts_cedex_and_cx(monkeypatch, tmp_path):
    path = tmp_path / "fr_communes.json"
    path.write_text(
        json.dumps([{"nom": "Drancy", "codesPostaux": ["93700"], "code": "93029"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTAL_REFERENCE_PATH", str(path))
    load_postal_reference.cache_clear()

    assert validate_postal_city("93700", "DRANCY CEDEX")["match"] is True
    assert validate_postal_city("93700", "DRANCY CX")["match"] is True


def test_validate_postal_city_accepts_hyphenated_official_city(monkeypatch, tmp_path):
    path = tmp_path / "fr_communes.json"
    path.write_text(
        json.dumps([{"nom": "Chambray-lès-Tours", "codesPostaux": ["37170"], "code": "37050"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTAL_REFERENCE_PATH", str(path))
    load_postal_reference.cache_clear()

    result = validate_postal_city("37170", "CHAMBRAY LES TOURS")

    assert result["status"] == "ok"
    assert result["match"] is True


def test_validate_postal_city_mismatch(monkeypatch, tmp_path):
    path = tmp_path / "fr_communes.json"
    path.write_text(
        json.dumps([{"nom": "Drancy", "codesPostaux": ["93700"], "code": "93029"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTAL_REFERENCE_PATH", str(path))
    load_postal_reference.cache_clear()

    result = validate_postal_city("93700", "PARIS")

    assert result["status"] == "ville_incompatible"
    assert result["match"] is False


def test_extract_postal_city_pairs_spaced_postal(monkeypatch, tmp_path):
    path = tmp_path / "fr_communes.json"
    path.write_text(
        json.dumps([{"nom": "Ascain", "codesPostaux": ["64310"], "code": "64065"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTAL_REFERENCE_PATH", str(path))
    load_postal_reference.cache_clear()

    from app.postal_reference import best_valid_postal_city_pair, extract_postal_city_pairs

    pairs = extract_postal_city_pairs("64 310 ASCAIN")
    assert any(item["postal"] == "64310" and item["match"] is True for item in pairs)
    best = best_valid_postal_city_pair("IZI confort - 64 310 ASCAIN")
    assert best["postal"] == "64310"
    assert best["city"] == "ASCAIN"


def test_validate_postal_city_accepts_cedex_postal(monkeypatch, tmp_path):
    path = tmp_path / "fr_communes.json"
    path.write_text(
        json.dumps([{"nom": "Dijon", "codesPostaux": ["21000"], "code": "21231"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTAL_REFERENCE_PATH", str(path))
    load_postal_reference.cache_clear()

    result = validate_postal_city("21076", "DIJON CEDEX")

    assert result["match"] is True
    assert result["status"] == "cedex_ok"


def test_extract_postal_city_pairs_glued_after_devise_prefix(monkeypatch, tmp_path):
    path = tmp_path / "fr_communes.json"
    path.write_text(
        json.dumps([{"nom": "Dijon", "codesPostaux": ["21000"], "code": "21231"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTAL_REFERENCE_PATH", str(path))
    load_postal_reference.cache_clear()

    from app.postal_reference import extract_postal_city_pairs

    pairs = extract_postal_city_pairs("Devise......... E 21076DIJON CEDEX")
    assert any(item["postal"] == "21076" and item.get("match") is True for item in pairs)


def test_rejects_invalid_postal_city_pair_devise(monkeypatch, tmp_path):
    path = tmp_path / "fr_communes.json"
    path.write_text(
        json.dumps([{"nom": "Corbie", "codesPostaux": ["80200"], "code": "80212"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTAL_REFERENCE_PATH", str(path))
    load_postal_reference.cache_clear()

    from app.postal_reference import best_valid_postal_city_pair, extract_postal_city_pairs

    assert best_valid_postal_city_pair("Devise 80200") is None
    assert not any(item.get("city") and item.get("match") is True for item in extract_postal_city_pairs("Devise 80200"))


def test_best_postal_city_prefers_matching_pair_in_noisy_text(monkeypatch, tmp_path):
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
    load_postal_reference.cache_clear()

    result = best_postal_city_in_text("LIVRAISON Zone Des Negadoux 3700 DRANCY 83140 SIX FOURS LES PLAGES")

    assert result["postal"] == "83140"
    assert result["city"] == "SIX FOURS LES PLAGES"


def test_invalid_city_token_rejects_street_type_and_street_prefix():
    from app.postal_reference import is_invalid_city_token, is_rejectable_postal_city_pair

    assert is_invalid_city_token("CHEMIN") is True
    assert is_invalid_city_token("CHEMIN", street="CHEMIN DE MONTREVEIL") is True
    assert is_rejectable_postal_city_pair("39120", "CHEMIN", street="CHEMIN DE MONTREVEIL") is True
