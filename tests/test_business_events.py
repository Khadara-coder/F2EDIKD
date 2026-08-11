"""Tests for métier / performance business events."""
from __future__ import annotations

from src.file2edi.router import _biz_field_changes
from src.file2edi.store import File2EdiStore


def test_log_and_list_business_events(tmp_path):
    store = File2EdiStore(str(tmp_path / "file2edi.db"), str(tmp_path / "intake"))

    created = store.log_business_event(
        actor="alice",
        action="order.hold",
        entity_type="order",
        entity_id="ord-1",
        order_id="ord-1",
        result="ok",
        duration_ms=42,
        details={"reason": "attente client"},
    )
    assert created["eventId"].startswith("biz-")
    assert created["action"] == "order.hold"
    assert created["durationMs"] == 42

    store.log_business_event(
        actor="bob",
        action="order.send_sap",
        order_id="ord-2",
        result="error",
        duration_ms=1200,
        details={"error": "timeout"},
    )

    all_events = store.list_business_events(limit=50)
    assert len(all_events) >= 2

    alice = store.list_business_events(actor="alice")
    assert len(alice) == 1
    assert alice[0]["details"]["reason"] == "attente client"

    searched = store.list_business_events(search="send_sap")
    assert len(searched) == 1
    assert searched[0]["result"] == "error"


def test_biz_field_changes_keeps_from_to():
    changes = _biz_field_changes(
        {"country": "FR", "postalCode": "69000", "city": "Lyon"},
        {"country": "DE", "postalCode": "69000", "editSource": "manual"},
    )
    assert changes == {"country": {"from": "FR", "to": "DE"}}
    assert "editSource" not in changes
    assert "postalCode" not in changes  # unchanged
