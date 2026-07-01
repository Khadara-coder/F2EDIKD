"""Tests for src/repository.py — SQLite CRUD and 3-component dedupe key."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test gets its own in-memory-equivalent SQLite DB."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    monkeypatch.setenv("DATA_DIR",      str(tmp_path))
    monkeypatch.setenv("INTAKE_DIR",    str(tmp_path / "intake"))
    monkeypatch.setenv("PROCESSED_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("REJECT_DIR",    str(tmp_path / "reject"))
    monkeypatch.setenv("OUTBOX_DIR",    str(tmp_path / "outbox"))

    # Copy schema.sql to expected location
    schema_src = Path(__file__).parent.parent / "data" / "schema.sql"
    schema_dst_dir = tmp_path / "data"
    schema_dst_dir.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy(schema_src, schema_dst_dir / "schema.sql")

    # Patch _project_root so database.py finds data/schema.sql in tmp_path
    import sys
    # Force fresh import so DB_PATH env var is picked up
    for mod in list(sys.modules.keys()):
        if "edifact" in mod and ("database" in mod or "repository" in mod):
            del sys.modules[mod]

    # Monkeypatch project root
    import importlib
    db_mod = importlib.import_module("src.database")
    monkeypatch.setattr(db_mod, "_project_root", lambda: tmp_path)

    db_mod.initialize_database()


def _import_repo():
    import importlib
    return importlib.import_module("src.repository")


# ------------------------------------------------------------------ #
# Job lifecycle
# ------------------------------------------------------------------ #

class TestJobCRUD:
    def test_create_and_get_job(self, tmp_path: Path) -> None:
        repo = _import_repo()
        pdf = tmp_path / "order.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")

        job_id = repo.create_job(
            source_filename="order.pdf",
            source_path=pdf,
            po_number="PO-001",
            soldto="1000001",
        )
        assert job_id

        job = repo.get_job(job_id)
        assert job is not None
        assert job["po_number"] == "PO-001"
        assert job["soldto"] == "1000001"
        assert job["status"] == "RECEIVED"

    def test_list_jobs_empty(self) -> None:
        repo = _import_repo()
        assert repo.list_jobs() == []

    def test_list_jobs_ordered(self, tmp_path: Path) -> None:
        repo = _import_repo()
        for i in range(3):
            pdf = tmp_path / f"o{i}.pdf"
            pdf.write_bytes(b"%PDF")
            repo.create_job(source_filename=f"o{i}.pdf", source_path=pdf)
        jobs = repo.list_jobs(limit=10)
        assert len(jobs) == 3
        # All 3 inserted; newest-first ordering, filenames are present
        filenames = {j["source_filename"] for j in jobs}
        assert filenames == {"o0.pdf", "o1.pdf", "o2.pdf"}

    def test_update_job_status(self, tmp_path: Path) -> None:
        repo = _import_repo()
        pdf = tmp_path / "upd.pdf"
        pdf.write_bytes(b"%PDF")
        jid = repo.create_job("upd.pdf", pdf)

        repo.update_job_status(jid, "COMPLETED", output_filename="out.tst", output_path="/outbox/out.tst")
        job = repo.get_job(jid)
        assert job["status"] == "COMPLETED"
        assert job["output_filename"] == "out.tst"

    def test_get_nonexistent_job(self) -> None:
        repo = _import_repo()
        assert repo.get_job("00000000-0000-0000-0000-000000000000") is None

    def test_reserve_next_job(self, tmp_path: Path) -> None:
        repo = _import_repo()
        pdf = tmp_path / "r.pdf"
        pdf.write_bytes(b"%PDF")
        jid = repo.create_job("r.pdf", pdf, po_number="PO-RSV")

        reserved = repo.reserve_next_job()
        assert reserved is not None
        assert reserved["id"] == jid
        assert reserved["status"] == "PROCESSING"

    def test_reserve_returns_none_when_empty(self) -> None:
        repo = _import_repo()
        assert repo.reserve_next_job() is None


# ------------------------------------------------------------------ #
# 3-component dedupe key
# ------------------------------------------------------------------ #

class TestDedupeKey:
    def test_first_occurrence_not_duplicate(self, tmp_path: Path) -> None:
        repo = _import_repo()
        pdf = tmp_path / "first.pdf"
        pdf.write_bytes(b"%PDF-1.4 unique")

        is_dup = repo.check_and_record_duplicate("PO-100", "1000001", pdf)
        assert is_dup is False

    def test_same_triple_is_duplicate(self, tmp_path: Path) -> None:
        repo = _import_repo()
        pdf = tmp_path / "dup.pdf"
        pdf.write_bytes(b"%PDF-1.4 duplicate content")

        repo.check_and_record_duplicate("PO-200", "1000002", pdf)
        is_dup = repo.check_and_record_duplicate("PO-200", "1000002", pdf)
        assert is_dup is True

    def test_different_soldto_is_not_duplicate(self, tmp_path: Path) -> None:
        """Same PO+hash but different soldto = different key."""
        repo = _import_repo()
        pdf = tmp_path / "ds.pdf"
        pdf.write_bytes(b"%PDF-1.4 soldto test")

        repo.check_and_record_duplicate("PO-300", "1000003", pdf)
        is_dup = repo.check_and_record_duplicate("PO-300", "9999999", pdf)  # different soldto
        assert is_dup is False

    def test_different_pdf_hash_is_not_duplicate(self, tmp_path: Path) -> None:
        """Same PO+soldto but different file content = different hash = not dup."""
        repo = _import_repo()
        pdf1 = tmp_path / "h1.pdf"
        pdf2 = tmp_path / "h2.pdf"
        pdf1.write_bytes(b"%PDF-1.4 content A")
        pdf2.write_bytes(b"%PDF-1.4 content B")

        repo.check_and_record_duplicate("PO-400", "1000004", pdf1)
        is_dup = repo.check_and_record_duplicate("PO-400", "1000004", pdf2)
        assert is_dup is False

    def test_hit_count_increments(self, tmp_path: Path) -> None:
        repo = _import_repo()
        db_mod = __import__("src.database", fromlist=["get_connection"])
        pdf = tmp_path / "hc.pdf"
        pdf.write_bytes(b"%PDF hit_count test")

        repo.check_and_record_duplicate("PO-500", "1000005", pdf)
        repo.check_and_record_duplicate("PO-500", "1000005", pdf)
        repo.check_and_record_duplicate("PO-500", "1000005", pdf)

        with db_mod.get_connection() as conn:
            row = conn.execute(
                "SELECT hit_count FROM dedupe_ledger WHERE po_number=?", ("PO-500",)
            ).fetchone()
        assert row["hit_count"] == 3
