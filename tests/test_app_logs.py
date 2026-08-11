"""Tests for src/app_logs.py (Paramètres → Logs)."""
from __future__ import annotations

import logging

from src import app_logs as al


def test_get_recent_logs_includes_ring_buffer(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    al.reset_ring_for_tests()
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    logging.getLogger("edifact.test.logs").setLevel(logging.DEBUG)
    logging.getLogger("edifact.test.logs").info("hello-logs-panel")

    payload = al.get_recent_logs(limit=50, level="INFO", search="hello-logs")
    assert payload["count"] >= 1
    assert any("hello-logs-panel" in (item.get("message") or "") for item in payload["items"])
    assert payload["logDir"] == str(tmp_path)


def test_get_recent_logs_reads_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    log_file = tmp_path / "edifact.log"
    log_file.write_text(
        "2026-08-11T10:00:00 [INFO    ] edifact.api: sync started\n"
        "2026-08-11T10:00:01 [ERROR   ] edifact.api: sync failed\n",
        encoding="utf-8",
    )

    payload = al.get_recent_logs(limit=20, level="ERROR", file_name="edifact.log")
    assert payload["count"] >= 1
    assert any(item.get("level") == "ERROR" for item in payload["items"])
    assert any(f["name"] == "edifact.log" for f in payload["files"])
