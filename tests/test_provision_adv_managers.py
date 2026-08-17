"""Tests for ADV manager provisioning from Partners CSV."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "provision_adv_managers_from_partners.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("provision_adv_managers", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pytest.importorskip("pandas")

mod = _load_script()

PARTNERS_CSV = """SOLDTO;SHIPTO;LAND1;NAME;ORT01;PSTLZ;STRAS;PARVW;Fonction-Partenaire;Gestionaire-ADV;Email-I.D;User-I.D;numero-personne
15021919;15021920;FR;SISCA;LYON;69000;1 RUE A;SH;15000617;LE GALL XAVIER;LEX1TC@BOSCH.COM;LEX1TC;1
15021919;15021921;FR;SISCA;LYON;69000;2 RUE B;SH;15000617;LE GALL XAVIER;LEX1TC@BOSCH.COM;LEX1TC;1
15015743;15015744;FR;PARTEDIS;NANTES;44000;3 RUE C;SH;15000613;HAMON ANNE-MARIE;HAA5TC@BOSCH.COM;HAA5TC;2
"""


def test_pick_column_normalizes_hyphenated_headers():
    cols = ["Fonction-Partenaire", "Gestionaire-ADV", "Email-I.D", "User-I.D"]
    assert mod._pick_column(cols, "Fonction Partenaire") == "Fonction-Partenaire"
    assert mod._pick_column(cols, "User-I.D", "User ID") == "User-I.D"
    assert mod._pick_column(cols, "missing") is None


def test_load_gestionnaires_dedupes_by_user_id(tmp_path: Path):
    csv_path = tmp_path / "10564_Partners.csv"
    csv_path.write_text(PARTNERS_CSV, encoding="utf-8")

    rows = mod._load_gestionnaires(csv_path)
    assert {row["username"] for row in rows} == {"lex1tc", "haa5tc"}
    xavier = next(row for row in rows if row["username"] == "lex1tc")
    assert xavier["sapId"] == "15000617"
    assert xavier["displayName"] == "LE GALL XAVIER"
    assert xavier["email"] == "LEX1TC@BOSCH.COM"


def test_load_soldto_to_sap_id(tmp_path: Path):
    csv_path = tmp_path / "10564_Partners.csv"
    csv_path.write_text(PARTNERS_CSV, encoding="utf-8")

    mapping = mod._load_soldto_to_sap_id(csv_path)
    assert mapping["15021919"] == "15000617"
    assert mapping["15015743"] == "15000613"
