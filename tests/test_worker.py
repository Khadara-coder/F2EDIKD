"""Tests for src/worker.py — job processing loop and dedupe gating."""
from __future__ import annotations

import importlib
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "worker_test.db"
    monkeypatch.setenv("DB_PATH",       str(db_file))
    monkeypatch.setenv("DATA_DIR",      str(tmp_path))
    monkeypatch.setenv("INTAKE_DIR",    str(tmp_path / "intake"))
    monkeypatch.setenv("PROCESSED_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("REJECT_DIR",    str(tmp_path / "reject"))
    monkeypatch.setenv("OUTBOX_DIR",    str(tmp_path / "outbox"))

    schema_src = Path(__file__).parent.parent / "data" / "schema.sql"
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy(schema_src, tmp_path / "data" / "schema.sql")

    db_mod = importlib.import_module("src.database")
    monkeypatch.setattr(db_mod, "_project_root", lambda: tmp_path)
    db_mod.initialize_database()


def _make_job(tmp_path: Path, filename: str = "order.pdf") -> dict:
    """Insert a queued job and return it."""
    repo = importlib.import_module("src.repository")
    pdf = tmp_path / filename
    pdf.write_bytes(b"%PDF-1.4 test content")
    jid = repo.create_job(source_filename=filename, source_path=pdf, po_number="PO-TEST")
    return repo.get_job(jid)


class TestRunOnce:
    def test_run_once_empty_queue_returns_false(self) -> None:
        worker = importlib.import_module("src.worker")
        assert worker.run_once() is False

    def test_run_once_completed_job(self, tmp_path: Path) -> None:
        """Worker calls engine_adapter and marks job COMPLETED."""
        _make_job(tmp_path)
        worker = importlib.import_module("src.worker")
        repo   = importlib.import_module("src.repository")

        completed_result = MagicMock()
        completed_result.status = "COMPLETED"
        completed_result.po_number = "PO-TEST"
        completed_result.soldto = "1000001"
        completed_result.output_content = "UNA:+.? 'UNB+UNOC:3+4399901876613+3015981600108+..."
        completed_result.output_filename = "ORDERS_1000001_POTEST_20260626.tst"
        completed_result.rejection_reason = None

        from src.sftp_delivery import SftpDeliveryResult
        mock_sftp_ok = SftpDeliveryResult(success=True, tst_filename="ORDERS_.tst", remote_path="/remote/ORDERS_.tst")
        with patch("src.worker.process_pdf_to_edifact", return_value=completed_result),              patch("src.worker.upload_tst", return_value=mock_sftp_ok):
            had_work = worker.run_once()

        assert had_work is True
        jobs = repo.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["status"] == "COMPLETED"

    def test_run_once_rejected_job(self, tmp_path: Path) -> None:
        _make_job(tmp_path)
        worker = importlib.import_module("src.worker")
        repo   = importlib.import_module("src.repository")

        rejected_result = MagicMock()
        rejected_result.status = "REJECTED"
        rejected_result.po_number = "PO-TEST"
        rejected_result.soldto = ""
        rejected_result.rejection_reason = "NO_VALID_ARTICLE"
        rejected_result.output_content = None
        rejected_result.output_filename = None

        with patch("src.worker.process_pdf_to_edifact", return_value=rejected_result):
            worker.run_once()

        jobs = repo.list_jobs()
        assert jobs[0]["status"] == "REJECTED"
        assert jobs[0]["rejection_reason"] == "NO_VALID_ARTICLE"

    def test_run_once_exception_marks_failed(self, tmp_path: Path) -> None:
        _make_job(tmp_path)
        worker = importlib.import_module("src.worker")
        repo   = importlib.import_module("src.repository")

        with patch("src.worker.process_pdf_to_edifact", side_effect=RuntimeError("boom")):
            worker.run_once()

        jobs = repo.list_jobs()
        assert jobs[0]["status"] == "FAILED"
        assert "boom" in (jobs[0]["error_message"] or "")


class TestDedupe:
    def test_duplicate_job_is_marked_duplicate(self, tmp_path: Path) -> None:
        """Two jobs with identical PO+soldto+hash should deduplicate on second run."""
        # Use two files with IDENTICAL content (same SHA-256) but different paths,
        # so job-1 can move pdf1 to processed/ without breaking job-2's hash.
        repo = importlib.import_module("src.repository")
        worker = importlib.import_module("src.worker")

        pdf_content = b"%PDF-1.4 duplicate pdf identical content"
        pdf1 = tmp_path / "dup0.pdf"
        pdf2 = tmp_path / "dup1.pdf"
        pdf1.write_bytes(pdf_content)
        pdf2.write_bytes(pdf_content)  # identical content -> same SHA-256

        repo.create_job("dup0.pdf", pdf1, po_number="PO-DUP")
        repo.create_job("dup1.pdf", pdf2, po_number="PO-DUP")

        completed = MagicMock()
        completed.status = "COMPLETED"
        completed.po_number = "PO-DUP"
        completed.soldto = "1000001"
        completed.output_content = "UNA:+.? '"
        completed.output_filename = "ORDERS_1000001_PODUP_20260626.tst"
        completed.rejection_reason = None

        from src.sftp_delivery import SftpDeliveryResult
        mock_sftp_ok = SftpDeliveryResult(success=True, tst_filename="ORDERS_.tst", remote_path="/remote/ORDERS_.tst")
        with patch("src.worker.process_pdf_to_edifact", return_value=completed),              patch("src.worker.upload_tst", return_value=mock_sftp_ok):
            worker.run_once()  # first → COMPLETED
            worker.run_once()  # second → DUPLICATE

        jobs = repo.list_jobs()
        statuses = {j["status"] for j in jobs}
        assert "COMPLETED" in statuses
        assert "DUPLICATE" in statuses
