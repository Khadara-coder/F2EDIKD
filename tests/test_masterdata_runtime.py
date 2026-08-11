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
    assert kind_key("salesorders") == "salesorders"


def test_import_dataframe_parquet(tmp_path, monkeypatch):
    import pandas as pd

    from src import masterdata_runtime as mdr

    monkeypatch.setattr(mdr, "runtime_dir", lambda: tmp_path)
    monkeypatch.setattr(mdr, "load_cache", lambda: {})

    df = pd.DataFrame(
        [
            {
                "SOLDTO": "15000000",
                "NAME": "ACME",
                "ORT01": "Paris",
                "PSTLZ": "75001",
                "STRAS": "1 rue A",
                "LAND1": "FR",
                "VAT_NR": "FR123",
            }
        ]
    )
    from io import BytesIO

    buf = BytesIO()
    df.to_parquet(buf, index=False)
    raw = buf.getvalue()

    out = mdr.import_dataframe("customers", raw, filename="10564_Customers.parquet")
    assert out["format"] == "parquet"
    assert out["rows"] == 1
    assert (tmp_path / "10564_Customers.csv").exists()
    assert (tmp_path / "10564_Customers.parquet").exists()


def test_dataframe_from_bytes_csv_still_works():
    from src.masterdata_runtime import dataframe_from_bytes

    raw = b"SOLDTO;NAME;ORT01;PSTLZ;STRAS;LAND1;VAT_NR\n1;A;B;C;D;FR;V\n"
    df = dataframe_from_bytes(raw, filename="x.csv")
    assert list(df.columns)[0] == "SOLDTO"
    assert df.iloc[0]["NAME"] == "A"


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


def test_material_line_status(monkeypatch):
    import pandas as pd

    from src import masterdata_runtime as mdr

    df = pd.DataFrame(
        [
            {"MATNR": "111", "MAKTX": "OK", "Statut": "Article disponible", "VMSTA": ""},
            {"MATNR": "222", "MAKTX": "STOP", "Statut": "no sale", "VMSTA": "92"},
            {"MATNR": "333", "MAKTX": "OLD", "Statut": "999888", "VMSTA": "97", "Commentaire": "14/02/2023"},
            {"MATNR": "999888", "MAKTX": "NEW", "Statut": "Article disponible", "VMSTA": ""},
            {"MATNR": "444", "MAKTX": "ALT", "Statut": "substitute, segmenti", "VMSTA": "97"},
        ]
    )
    monkeypatch.setitem(mdr.CACHE, "materials", {"df": df, "rows": 5})

    avail = mdr.material_line_status("111")
    assert avail["kind"] == "available"
    assert avail["found"] is True

    stopped = mdr.material_line_status("222")
    assert stopped["kind"] == "no_sale"

    replaced = mdr.material_line_status("333")
    assert replaced["kind"] == "replacement"
    assert replaced["replacement"] == "999888"
    assert replaced["replacement_since"] == "14/02/2023"
    assert mdr.material_status_replacement("333") == "999888"

    enriched = mdr.format_materials(
        [{"MATNR": "333", "MAKTX": "OLD", "Statut": "999888", "Commentaire": "14/02/2023"}]
    )
    assert enriched[0]["fields"]["Commentaire"] == (
        "Cette référence a été remplacée depuis le 14/02/2023 par 999888"
    )

    other = mdr.material_line_status("444")
    assert other["kind"] == "available"

    missing = mdr.material_line_status("missing")
    assert missing["kind"] == "missing"
    assert missing["found"] is False
    assert mdr.material_status_replacement("missing") is None


def test_material_line_status_chain(monkeypatch):
    import pandas as pd

    from src import masterdata_runtime as mdr

    df = pd.DataFrame(
        [
            {"MATNR": "100001", "MAKTX": "A", "Statut": "200002", "VMSTA": "97"},
            {"MATNR": "200002", "MAKTX": "B", "Statut": "300003", "VMSTA": "97"},
            {"MATNR": "300003", "MAKTX": "C", "Statut": "Article disponible", "VMSTA": ""},
        ]
    )
    monkeypatch.setitem(mdr.CACHE, "materials", {"df": df, "rows": 3})

    status = mdr.material_line_status("100001")
    assert status["kind"] == "replacement"
    assert status["replacement"] == "300003"
    assert status["replacement_chain"] == ["100001", "200002", "300003"]


def test_material_line_status_chain_no_sale_final(monkeypatch):
    import pandas as pd

    from src import masterdata_runtime as mdr

    df = pd.DataFrame(
        [
            {"MATNR": "100001", "MAKTX": "A", "Statut": "200002", "VMSTA": "97"},
            {"MATNR": "200002", "MAKTX": "B", "Statut": "no sale", "VMSTA": "92"},
        ]
    )
    monkeypatch.setitem(mdr.CACHE, "materials", {"df": df, "rows": 2})

    status = mdr.material_line_status("100001")
    assert status["kind"] == "no_sale"
    assert status["replacement"] == "200002"
    assert status.get("via_replacement") is True


def test_material_line_status_replacement_cycle(monkeypatch):
    import pandas as pd

    from src import masterdata_runtime as mdr

    df = pd.DataFrame(
        [
            {"MATNR": "100001", "MAKTX": "A", "Statut": "200002", "VMSTA": "97"},
            {"MATNR": "200002", "MAKTX": "B", "Statut": "100001", "VMSTA": "97"},
        ]
    )
    monkeypatch.setitem(mdr.CACHE, "materials", {"df": df, "rows": 2})

    status = mdr.material_line_status("100001")
    assert status["kind"] == "replacement"
    assert status.get("replacement_cycle") is True
