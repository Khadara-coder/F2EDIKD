from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.engine import FullCodeEngine, get_engine
from app.runtime import configure_runtime


@pytest.fixture(autouse=True)
def runtime_env(monkeypatch, tmp_path):
    master = tmp_path / "masterdata"
    master.mkdir()
    for name in ("10564_Customers.csv", "10564_Partners.csv", "10564_Materials.csv", "DB_Salesorder.csv"):
        src = Path(__file__).resolve().parents[1] / "data" / "masterdata" / name
        if src.exists():
            (master / name).write_bytes(src.read_bytes())
    monkeypatch.setenv("MASTER_DATA_DIR", str(master))
    monkeypatch.setenv("ENABLE_ADDRESS_EMBEDDINGS", "false")
    configure_runtime()


def test_engine_health():
    engine = get_engine(ocr_enabled=False)
    status = engine.health()
    assert status["engine"] == "full_code"
    assert "master_data_loaded" in status


def test_engine_extract_pdf_izi_confort():
    import fitz

    text = (Path(__file__).parent / "fixtures" / "golden" / "01_izi_confort_order" / "input.txt").read_text(
        encoding="utf-8"
    )
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    payload = document.tobytes()

    engine = FullCodeEngine(ocr_enabled=False)
    response = engine.extract_pdf(payload, filename="order.pdf", pages="1", instruction="Extraire commande")
    structured = response["results"][0]["fields"]["structured"]
    assert structured["document"]["Numero de commande"] == "CM-00302553"
