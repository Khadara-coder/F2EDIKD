"""Tests for src/api.py — FastAPI endpoints."""
from __future__ import annotations

import importlib
import shutil
from pathlib import Path

import pytest

try:
    from fastapi.testclient import TestClient
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

pytest.importorskip("fastapi", reason="fastapi not installed")


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Provide a TestClient backed by an isolated SQLite DB."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH",       str(db_file))
    monkeypatch.setenv("DATA_DIR",      str(tmp_path))
    monkeypatch.setenv("INTAKE_DIR",    str(tmp_path / "intake"))
    monkeypatch.setenv("PROCESSED_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("REJECT_DIR",    str(tmp_path / "reject"))
    monkeypatch.setenv("OUTBOX_DIR",    str(tmp_path / "outbox"))

    # Provide schema.sql in expected location
    schema_src = Path(__file__).parent.parent / "data" / "schema.sql"
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy(schema_src, tmp_path / "data" / "schema.sql")

    # Patch _project_root
    db_mod = importlib.import_module("src.database")
    monkeypatch.setattr(db_mod, "_project_root", lambda: tmp_path)

    api_mod = importlib.import_module("src.api")
    app = api_mod._build_app()  # fresh app with patched DB

    from fastapi.testclient import TestClient
    with TestClient(app) as tc:
        yield tc


class TestHealthEndpoint:
    def test_health_returns_ok(self, client) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "edifact-standalone"
        assert body["unb_profile"] == "ELM_STANDARD"
        # Forbidden values must not appear in health response
        assert "3020810000707" not in str(body)
        assert "54209794400681" not in str(body)


class TestJobsEndpoint:
    def test_upload_non_pdf_rejected(self, client) -> None:
        resp = client.post(
            "/jobs",
            files={"pdf": ("doc.txt", b"not a pdf", "text/plain")},
        )
        assert resp.status_code == 400

    def test_upload_pdf_returns_received(self, client) -> None:
        resp = client.post(
            "/jobs",
            files={"pdf": ("order.pdf", b"%PDF-1.4 test", "application/pdf")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "RECEIVED"
        assert "job_id" in body

    def test_list_jobs_empty(self, client) -> None:
        resp = client.get("/jobs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_jobs_after_upload(self, client) -> None:
        client.post(
            "/jobs",
            files={"pdf": ("a.pdf", b"%PDF-1.4", "application/pdf")},
        )
        resp = client.get("/jobs")
        assert len(resp.json()) == 1

    def test_get_job_by_id(self, client) -> None:
        upload = client.post(
            "/jobs",
            files={"pdf": ("b.pdf", b"%PDF-1.4", "application/pdf")},
        ).json()
        job_id = upload["job_id"]

        resp = client.get(f"/jobs/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == job_id

    def test_get_unknown_job_404(self, client) -> None:
        resp = client.get("/jobs/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404


class TestRetryEndpoint:
    def test_retry_nonexistent_job_404(self, client) -> None:
        resp = client.post("/jobs/00000000-0000-0000-0000-000000000000/retry")
        assert resp.status_code == 404

    def test_retry_received_job_returns_409(self, client) -> None:
        upload = client.post(
            "/jobs",
            files={"pdf": ("c.pdf", b"%PDF-1.4", "application/pdf")},
        ).json()
        job_id = upload["job_id"]

        # RECEIVED jobs cannot be retried (only FAILED/REJECTED)
        resp = client.post(f"/jobs/{job_id}/retry")
        assert resp.status_code == 409
