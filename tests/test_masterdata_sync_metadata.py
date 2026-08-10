"""Tests for masterdata sync metadata bump (UI last-sync stamp)."""
from __future__ import annotations

from pathlib import Path

from src import masterdata_runtime as mdr


def test_bump_sync_metadata_updates_file_and_freshness(tmp_path: Path, monkeypatch):
    runtime = tmp_path / "masterdata"
    runtime.mkdir()
    meta_path = runtime / ".masterdata_sync_metadata.json"
    meta_path.write_text(
        '{"synced_at_utc":"2026-08-06T07:26:28Z","commit":"9a0aea19","files":{}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("MASTERDATA_RUNTIME_DIR", str(runtime))
    mdr.configure(runtime_dir=str(runtime), source_dir=str(runtime), metadata_path=str(meta_path))
    mdr.MD_LAST_SYNC.clear()

    before = mdr.sync_freshness()
    assert before["synced_at_utc"] == "2026-08-06T07:26:28Z"
    assert before["status"] == "stale"

    bumped = mdr.bump_sync_metadata(
        synced_at_utc="2026-08-10T14:30:00Z",
        commit="abc12345",
        source="test",
    )
    assert bumped["synced_at_utc"] == "2026-08-10T14:30:00Z"

    after = mdr.sync_freshness()
    assert after["synced_at_utc"] == "2026-08-10T14:30:00Z"
    assert after["commit"] == "abc12345"
    assert after["status"] == "fresh"
