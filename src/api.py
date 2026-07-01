"""FastAPI application for EDIFACT Standalone Orchestrator.

Endpoints:
  GET  /health            — service health + config summary
  POST /jobs              — submit a PDF for processing
  GET  /jobs              — list recent jobs
  GET  /jobs/{job_id}     — get job detail
  POST /jobs/{job_id}/retry — requeue a failed/rejected job
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from .config_loader import load_config
from .database import initialize_database
from .repository import create_job, get_job, list_jobs, update_job_status


class RetryResponse(BaseModel):
    job_id: str
    status: str


def _get_intake_dir() -> Path:
    root = Path(__file__).resolve().parent.parent
    p = Path(os.getenv("INTAKE_DIR", str(root / "data" / "intake")))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _build_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ARG001
        initialize_database()
        yield

    app = FastAPI(
        title="EDIFACT Standalone Orchestrator",
        description="PDF → EDIFACT ORDERS D.96A → SFTP — ELM_STANDARD only",
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict:
        """Service health check and config summary."""
        cfg = load_config()
        return {
            "status": "ok",
            "service": "edifact-standalone",
            "unb_profile": cfg.edi.unb_profile,
            "sender_id": cfg.edi.sender_id,
            "receiver_id": cfg.edi.receiver_id,
            "sftp_enabled": str(cfg.sftp.enabled).lower(),
            "masterdata_root": cfg.masterdata.masterdata_root,
        }

    @app.post("/jobs")
    async def create_job_from_pdf(
        pdf: UploadFile = File(...),
        po_number: str | None = None,
    ) -> dict:
        """Accept a PDF upload and queue it for processing."""
        if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Upload must be a .pdf file")

        saved_name = f"{uuid.uuid4().hex}.pdf"
        saved_path = _get_intake_dir() / saved_name
        saved_path.write_bytes(await pdf.read())

        job_id = create_job(
            source_filename=pdf.filename,
            source_path=saved_path,
            po_number=po_number,
        )
        return {"job_id": job_id, "status": "RECEIVED", "source_path": str(saved_path)}

    @app.get("/jobs")
    def read_jobs(limit: int = 100) -> list[dict]:
        """List recent jobs, newest first."""
        return list_jobs(limit=limit)

    @app.get("/jobs/{job_id}")
    def read_job(job_id: str) -> dict:
        """Return a single job by UUID."""
        job = get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    @app.post("/jobs/{job_id}/retry", response_model=RetryResponse)
    def retry_job(job_id: str) -> RetryResponse:
        """Requeue a FAILED or REJECTED job."""
        job = get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        if job["status"] not in {"FAILED", "REJECTED"}:
            raise HTTPException(
                status_code=409,
                detail=f"Only FAILED or REJECTED jobs can be retried; current status: {job['status']}",
            )
        update_job_status(job_id, "RETRY", error_message=None)
        return RetryResponse(job_id=job_id, status="RETRY")

    return app


app = _build_app()
