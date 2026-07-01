from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "regression" / "manifest.yaml"
CORPUS = ROOT / "data" / "corpus" / "rag-purchase-orders"
REGRESSION = ROOT / "data" / "regression" / "pdfs"


def load_manifest() -> dict:
    assert MANIFEST.exists(), "data/regression/manifest.yaml manquant"
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def test_regression_manifest_lists_thirty_cases():
    manifest = load_manifest()
    cases = manifest.get("cases") or []
    assert len(cases) == 30
    ids = [item["id"] for item in cases]
    assert len(ids) == len(set(ids))


def test_regression_manifest_files_unique():
    manifest = load_manifest()
    files = [item["file"] for item in manifest.get("cases", [])]
    assert len(files) == len(set(files))


@pytest.mark.skipif(not CORPUS.exists(), reason="corpus non présent localement")
def test_regression_sources_exist_in_corpus():
    manifest = load_manifest()
    missing = []
    for case in manifest.get("cases", []):
        path = CORPUS / case["file"]
        if not path.exists():
            missing.append(case["file"])
    assert not missing, f"PDF manquants dans le corpus : {missing[:5]}"


@pytest.mark.skipif(not REGRESSION.exists(), reason="jeu de régression non construit")
def test_regression_pdfs_built():
    manifest = load_manifest()
    missing = []
    for case in manifest.get("cases", []):
        path = REGRESSION / case["file"]
        if not path.exists():
            missing.append(case["file"])
    assert not missing, f"Exécutez scripts/build_regression_set.ps1 — manquants : {missing[:5]}"
