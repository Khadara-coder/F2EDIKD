from __future__ import annotations

from app.masterdata import city_compatible, street_similarity
from app.text_utils import norm_key, normalize_address_compare


def test_normalize_address_compare_strips_accents_and_punctuation():
    assert normalize_address_compare("28, rue de Mayence - ZAË Capnord") == "28 rue de mayence zae capnord"
    assert normalize_address_compare("Saint-Étienne") == "saint etienne"


def test_norm_key_ignores_punctuation_and_accents():
    assert norm_key("Z.A. LANZELAI") == norm_key("ZA LANZELAI")
    assert norm_key("28, rue de Mayence") == norm_key("28 RUE DE MAYENCE")


def test_street_similarity_ignores_commas_hyphens_and_accents():
    assert street_similarity("28, rue de Mayence - ZAË", "28 RUE DE MAYENCE ZAE") >= 0.88
    assert street_similarity("Z.A. LANZELAI", "ZA LANZELAI") >= 0.95


def test_city_compatible_ignores_hyphens_and_accents():
    assert city_compatible("Saint-Étienne", "SAINT ETIENNE")
    assert city_compatible("CHAMBRAY-LÈS-TOURS", "CHAMBRAY LES TOURS")
