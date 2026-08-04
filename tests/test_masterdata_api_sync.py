"""Tests for Databricks Apps masterdata API sync helpers."""

from __future__ import annotations

import json
from pathlib import Path

from src.masterdata_api_sync import (
    _extract_rows,
    _write_csv,
    default_config,
    resolve_config,
    sync_from_api,
)


def test_resolve_config_defaults_and_paths():
    cfg = resolve_config({"baseUrl": "https://example.test/", "pageSize": 50})
    assert cfg["baseUrl"] == "https://example.test"
    assert cfg["pageSize"] == 100  # clamped min
    assert cfg["customersPath"].startswith("/")


def test_extract_rows_supports_common_payload_shapes():
    assert len(_extract_rows([{"SOLDTO": "1"}])) == 1
    assert len(_extract_rows({"items": [{"SOLDTO": "1"}, {"SOLDTO": "2"}]})) == 2
    assert len(_extract_rows({"customers": [{"SOLDTO": "1"}]})) == 1


def test_write_csv_uses_semicolon_and_required_columns(tmp_path: Path):
    out = tmp_path / "10564_Customers.csv"
    n = _write_csv(
        out,
        ["SOLDTO", "NAME", "ORT01", "PSTLZ", "STRAS", "LAND1", "VAT_NR"],
        [{"soldto": "150", "NAME": "ACME", "ORT01": "LYON"}],
    )
    assert n == 1
    text = out.read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("SOLDTO;NAME;")
    assert "150;ACME;LYON" in text


def test_sync_from_api_writes_four_files(monkeypatch, tmp_path: Path):
    class FakeResp:
        def __init__(self, payload, status=200):
            self.status_code = status
            self._payload = payload
            self.headers = {"content-type": "application/json"}
            self.text = json.dumps(payload)

        def json(self):
            return self._payload

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None, params=None, timeout=None):
            if url.endswith("/health"):
                return FakeResp({"ok": True})
            if "/customers" in url:
                return FakeResp([{"SOLDTO": "1", "NAME": "A", "ORT01": "X", "PSTLZ": "1", "STRAS": "R", "LAND1": "FR", "VAT_NR": "V"}])
            if "/partners" in url:
                return FakeResp([{"SOLDTO": "1", "SHIPTO": "1", "LAND1": "FR", "NAME": "A", "ORT01": "X", "PSTLZ": "1", "STRAS": "R", "PARVW": "SH"}])
            if "/materials" in url:
                return FakeResp([{"MATNR": "M1", "MAKTX": "Item"}])
            if "/salesorders" in url:
                return FakeResp([{"VBELN": "V1", "ERDAT": "20260101", "ERNAM": "U", "BSTNK": "PO", "BSTDK": "20260101", "KUNNR": "1"}])
            return FakeResp([], status=404)

    monkeypatch.setenv("DATABRICKS_TOKEN", "test-token")
    monkeypatch.setattr("requests.Session", lambda: FakeSession())

    target = tmp_path / "masterdata"
    result = sync_from_api(target_dir=target, config=default_config())
    assert result["status"] == "ok"
    assert (target / "10564_Customers.csv").exists()
    assert (target / "10564_Partners.csv").exists()
    assert (target / "10564_Materials.csv").exists()
    assert (target / "DB_Salesorder.csv").exists()
    assert result["files"]["10564_Customers.csv"]["rows"] == 1
