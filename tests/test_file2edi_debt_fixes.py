"""Tech-debt regression: sap_sent_at, hide done statuses, cascade delete upload."""

from __future__ import annotations

from pathlib import Path

from src.file2edi.store import File2EdiStore


def _minimal_review(order_id: str, upload_id: str, status: str = "Revue requise") -> dict:
    return {
        "order": {
            "orderId": order_id,
            "uploadId": upload_id,
            "fileName": f"{order_id}.pdf",
            "clientName": "Client Test",
            "customerOrderNumber": "PO-1",
            "documentReference": "PO-1",
            "orderDate": "2026-08-05",
            "requestedDeliveryDate": "2026-08-06",
            "currency": "EUR",
            "incoterm": "DAP",
            "deliveryMode": "Messagerie",
            "messageType": "ORDERS",
            "vendor": "CM1",
            "totalAmount": 10,
            "globalConfidence": 100,
            "status": status,
            "reviewRequired": True,
            "lineCount": 0,
            "createdAt": "2026-08-05T10:00:00+00:00",
            "updatedAt": "2026-08-05T10:00:00+00:00",
        },
        "partners": [],
        "lines": [],
        "anomalies": [],
    }


def test_mark_sftp_delivery_sets_sap_sent_at(tmp_path: Path):
    store = File2EdiStore(str(tmp_path / "f2e.db"), str(tmp_path / "intake"))
    store.save_order_review(_minimal_review("ord-sap", "upl-sap"))
    store.mark_sftp_delivery("ord-sap", True, "/remote/ORDERS.tst")

    rows = store.list_orders_summary()
    # Envoyé SAP is filtered out of the work queue
    assert all(r["order_id"] != "ord-sap" for r in rows)

    conn = store._conn()
    row = conn.execute(
        "SELECT status, sap_sent_at FROM file2edi_orders WHERE order_id=?",
        ["ord-sap"],
    ).fetchone()
    conn.close()
    assert row["status"] == "Envoyé SAP"
    assert row["sap_sent_at"]


def test_list_orders_summary_hides_done_statuses(tmp_path: Path):
    store = File2EdiStore(str(tmp_path / "f2e.db"), str(tmp_path / "intake"))
    store.save_order_review(_minimal_review("ord-open", "upl-open", "Revue requise"))
    store.save_order_review(_minimal_review("ord-gen", "upl-gen", "Généré"))
    store.save_order_review(_minimal_review("ord-tr", "upl-tr", "Transféré"))
    store.save_order_review(_minimal_review("ord-hold", "upl-hold", "En attente"))
    store.save_order_review(_minimal_review("ord-sap", "upl-sap", "Envoyé SAP"))
    store.save_order_review(_minimal_review("ord-ok", "upl-ok", "Confirmé SAP"))

    ids = {r["order_id"] for r in store.list_orders_summary()}
    assert "ord-open" in ids
    assert "ord-gen" in ids
    assert "ord-tr" in ids
    assert "ord-hold" in ids
    assert "ord-sap" not in ids
    assert "ord-ok" not in ids


def test_delete_upload_cascades_orders_and_file(tmp_path: Path):
    intake = tmp_path / "intake"
    intake.mkdir()
    pdf = intake / "upl-del.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    store = File2EdiStore(str(tmp_path / "f2e.db"), str(intake))
    conn = store._conn()
    conn.execute(
        "INSERT INTO file2edi_pdf_uploads (upload_id, file_name, file_size, file_path, uploaded_at, uploaded_by, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ["upl-del", "upl-del.pdf", pdf.stat().st_size, str(pdf), "2026-08-05T10:00:00Z", "operator", "RECEIVED"],
    )
    conn.commit()
    conn.close()

    store.save_order_review(_minimal_review("ord-del", "upl-del"))
    assert store.delete_upload("upl-del") is True
    assert store.delete_upload("upl-del") is False
    assert not pdf.exists()

    conn = store._conn()
    assert conn.execute("SELECT COUNT(*) AS c FROM file2edi_orders WHERE upload_id=?", ["upl-del"]).fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) AS c FROM file2edi_pdf_uploads WHERE upload_id=?", ["upl-del"]).fetchone()["c"] == 0
    conn.close()
