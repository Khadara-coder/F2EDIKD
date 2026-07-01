from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault(
    "MASTER_DATA_DIR",
    str(Path(__file__).resolve().parents[1] / "data" / "masterdata"),
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "golden"
DEFAULT_POSTAL_REFERENCE = Path(__file__).resolve().parents[1] / "data" / "reference" / "fr_communes.json"


@pytest.fixture(autouse=True)
def reset_postal_reference_between_tests(monkeypatch):
    import app.postal_reference as postal_reference

    if DEFAULT_POSTAL_REFERENCE.exists():
        monkeypatch.setenv("POSTAL_REFERENCE_PATH", str(DEFAULT_POSTAL_REFERENCE))
    postal_reference.load_postal_reference.cache_clear()
    yield
    postal_reference.load_postal_reference.cache_clear()


@pytest.fixture(scope="session")
def master_data_ready():
    import app.masterdata as md

    md.master_data_cache = None
    md.master_data_cache_fingerprint = None
    data = md.get_master_data()
    if not data.get("loaded"):
        pytest.skip(f"Master data unavailable: {data.get('error', 'unknown')}")
    return data
