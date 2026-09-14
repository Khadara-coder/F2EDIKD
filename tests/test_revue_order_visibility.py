"""Tests for Revue ownership and submitter traceability."""

from src.file2edi.store import File2EdiStore

from src.file2edi.router import _actor_matches_order, _order_list_item


def test_my_orders_matches_any_lifecycle_actor_field():
    base = {
        "uploaded_by": "other",
        "processed_by": "system",
        "assigned_to": "other-adv",
        "sap_sent_by": "other-admin",
    }

    assert _actor_matches_order({**base, "uploaded_by": "adv"}, "adv")
    assert _actor_matches_order({**base, "processed_by": "adv"}, "adv")
    assert _actor_matches_order({**base, "assigned_to": "adv"}, "adv")
    assert _actor_matches_order({**base, "sap_sent_by": "adv"}, "adv")
    assert not _actor_matches_order(base, "adv")


def test_order_list_exposes_submitted_by_separately_from_processed_by():
    row = _order_list_item({
        "order_id": "ord-1",
        "file_name": "order.pdf",
        "client_name": "Client",
        "global_confidence": 90,
        "status": "À revoir",
        "created_at": "2026-09-14T10:00:00+00:00",
        "updated_at": "2026-09-14T10:00:00+00:00",
        "uploaded_by": "khadara",
        "processed_by": "system",
    })

    assert row["submittedBy"] == "khadara"
    assert row["processedBy"] == "system"


def test_upload_submitter_is_persisted_on_order(tmp_path):
    intake = tmp_path / "intake"
    intake.mkdir()
    pdf_path = intake / "upload.pdf"
    pdf_path.write_bytes(b"%PDF")
    store = File2EdiStore(str(tmp_path / "file2edi.db"), str(intake))
    review = {
        "order": {
            "orderId": "ord-submitter",
            "uploadId": "upl-submitter",
            "fileName": "upload.pdf",
            "clientName": "Client",
            "customerOrderNumber": "PO-1",
            "documentReference": "PO-1",
            "status": "À revoir",
            "reviewRequired": True,
            "lineCount": 0,
            "totalAmount": 0,
            "globalConfidence": 0,
            "pdfPath": str(pdf_path),
        },
        "partners": [],
        "lines": [],
        "anomalies": [],
    }
    store.save_upload_with_id("upl-submitter", "upload.pdf", 4, str(pdf_path), uploaded_by="adv")
    store.save_order_review(review)

    conn = store._conn()
    row = conn.execute(
        "SELECT uploaded_by FROM file2edi_orders WHERE order_id=?", ["ord-submitter"]
    ).fetchone()
    conn.close()
    assert row["uploaded_by"] == "adv"