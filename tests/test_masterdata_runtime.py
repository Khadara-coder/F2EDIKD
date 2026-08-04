"""Unit tests for masterdata_runtime pure helpers."""

from __future__ import annotations

from src.masterdata_runtime import (
    format_materials,
    kind_key,
    match_keys,
    normalize_article_code,
    row_value,
    validate_schema,
)


def test_row_value_case_insensitive():
    row = {"SoldTo": "15000000", "NAME": "ACME"}
    assert row_value(row, "SOLDTO", "soldto") == "15000000"
    assert row_value(row, "name") == "ACME"
    assert row_value(row, "missing") == ""


def test_kind_key_mapping():
    assert kind_key("clients") == "customers"
    assert kind_key("shipto") == "partners"
    assert kind_key("articles") == "materials"


def test_kind_key_unknown():
    try:
        kind_key("unknown")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "inconnu" in str(exc)


def test_normalize_article_code_strips_leading_zeros():
    assert normalize_article_code("000123") == "123"
    assert normalize_article_code("ABC") == "ABC"


def test_match_keys_includes_email_local_part():
    keys = match_keys("jean.dupont@bosch.com")
    assert any("JEAN" in k for k in keys)


def test_format_materials():
    rows = [{"MATNR": "123", "MAKTX": "Widget"}]
    out = format_materials(rows, sync_at="2026-01-01T00:00:00Z")
    assert out[0]["materialId"] == "123"
    assert out[0]["description"] == "Widget"


def test_validate_schema_materials():
    class _DF:
        columns = ["MATNR", "MAKTX"]

    info = validate_schema("materials", _DF())
    assert info["schema_valid"] is True
