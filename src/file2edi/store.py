"""File2EDI persistence — SQLite (+ optional Delta sync via server persistence adapter)."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "data" / "file2edi_schema.sql"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class File2EdiStore:
    def __init__(self, db_path: str, intake_dir: str) -> None:
        self.db_path = db_path
        self.intake_dir = Path(intake_dir)
        self.intake_dir.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _execute_write(self, fn):
        """Retry writes when SQLite is contended (dashboard polling, etc.)."""
        last_err: Exception | None = None
        for attempt in range(5):
            try:
                return fn()
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                last_err = exc
                time.sleep(0.05 * (attempt + 1))
        if last_err:
            raise last_err
        raise RuntimeError("write failed")

    def _init_schema(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        conn = self._conn()
        conn.executescript(sql)
        cols = {
            r[1]
            for r in conn.execute("PRAGMA table_info(file2edi_order_partners)").fetchall()
        }
        if "edited_fields_json" not in cols:
            conn.execute(
                "ALTER TABLE file2edi_order_partners ADD COLUMN edited_fields_json TEXT"
            )
        conn.commit()
        conn.close()

    def get_pdf_path_for_order(self, order_id: str) -> Path | None:
        """Resolve PDF file: order.pdf_path, then upload intake file."""
        conn = self._conn()
        row = conn.execute(
            "SELECT pdf_path, upload_id, file_name FROM file2edi_orders WHERE order_id=?",
            [order_id],
        ).fetchone()
        conn.close()
        if not row:
            return None
        if row["pdf_path"]:
            p = Path(row["pdf_path"])
            if p.exists():
                return p
        if row["upload_id"]:
            up = self.get_upload_path(row["upload_id"])
            if up:
                return up
        # Legacy intake naming: upl-*.pdf
        for candidate in self.intake_dir.glob("*.pdf"):
            if row["file_name"] and row["file_name"].lower() in candidate.name.lower():
                return candidate
        return None

    def ensure_order_pdf(self, order_id: str) -> Path | None:
        """Attach PDF path to order if missing but file exists on disk."""
        path = self.get_pdf_path_for_order(order_id)
        if not path:
            return None
        conn = self._conn()
        conn.execute(
            "UPDATE file2edi_orders SET pdf_path=?, updated_at=? WHERE order_id=?",
            [str(path), _now(), order_id],
        )
        conn.commit()
        conn.close()
        return path

    def save_upload(self, file_name: str, file_size: int, file_path: str, uploaded_by: str = "operator") -> dict:
        upload_id = f"upl-{uuid.uuid4().hex[:12]}"
        return self.save_upload_with_id(upload_id, file_name, file_size, file_path, uploaded_by)

    def save_upload_with_id(
        self,
        upload_id: str,
        file_name: str,
        file_size: int,
        file_path: str,
        uploaded_by: str = "operator",
    ) -> dict:
        def _write() -> dict:
            conn = self._conn()
            try:
                conn.execute(
                    """INSERT INTO file2edi_pdf_uploads
                    (upload_id,file_name,file_size,file_path,uploaded_at,uploaded_by,status)
                    VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(upload_id) DO UPDATE SET
                      file_name=excluded.file_name,
                      file_size=excluded.file_size,
                      file_path=excluded.file_path,
                      uploaded_at=excluded.uploaded_at""",
                    [upload_id, file_name, file_size, file_path, _now(), uploaded_by, "RECEIVED"],
                )
                conn.commit()
            finally:
                conn.close()
            return {"uploadId": upload_id, "fileName": file_name, "fileSize": file_size}

        return self._execute_write(_write)

    def get_upload_meta(self, upload_id: str) -> dict | None:
        conn = self._conn()
        row = conn.execute(
            "SELECT upload_id, file_name, file_size, file_path, uploaded_at, status"
            " FROM file2edi_pdf_uploads WHERE upload_id=?",
            [upload_id],
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_upload_path(self, upload_id: str) -> Path | None:
        conn = self._conn()
        row = conn.execute(
            "SELECT file_path FROM file2edi_pdf_uploads WHERE upload_id=?", [upload_id]
        ).fetchone()
        conn.close()
        if not row:
            return None
        p = Path(row["file_path"])
        return p if p.exists() else None

    def save_order_review(self, review: dict) -> None:
        review = dict(review)

        def _write() -> None:
            o = review["order"]
            conn = self._conn()
            engine = review.pop("_engine_result", None)
            pdf_path = o.get("pdfPath") or o.get("pdf_path")
            if not pdf_path and o.get("uploadId"):
                up = self.get_upload_path(o["uploadId"])
                if up:
                    pdf_path = str(up)
            try:
                conn.execute(
                    """INSERT INTO file2edi_orders (
                      order_id,upload_id,file_name,client_name,customer_order_number,document_reference,
                      order_date,requested_delivery_date,currency,incoterm,delivery_mode,message_type,vendor,
                      total_amount,global_confidence,status,review_required,line_count,pdf_hash,pdf_path,
                      extraction_json,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(order_id) DO UPDATE SET
                      upload_id=excluded.upload_id,
                      file_name=excluded.file_name,
                      client_name=excluded.client_name,
                      customer_order_number=excluded.customer_order_number,
                      document_reference=excluded.document_reference,
                      order_date=excluded.order_date,
                      requested_delivery_date=excluded.requested_delivery_date,
                      currency=excluded.currency,
                      incoterm=excluded.incoterm,
                      delivery_mode=excluded.delivery_mode,
                      total_amount=excluded.total_amount,
                      global_confidence=excluded.global_confidence,
                      status=excluded.status,
                      review_required=excluded.review_required,
                      line_count=excluded.line_count,
                      pdf_path=excluded.pdf_path,
                      extraction_json=excluded.extraction_json,
                      updated_at=excluded.updated_at
                    """,
                    [
                        o["orderId"], o["uploadId"], o["fileName"], o["clientName"],
                        o["customerOrderNumber"], o["documentReference"],
                        o.get("orderDate"), o.get("requestedDeliveryDate"),
                        o.get("currency", "EUR"), o.get("incoterm", "DAP"), o.get("deliveryMode"),
                        o.get("messageType", "ORDERS"), o.get("vendor"),
                        o.get("totalAmount", 0), o.get("globalConfidence", 0),
                        o.get("status"), 1 if o.get("reviewRequired") else 0,
                        o.get("lineCount", 0),
                        (engine or {}).get("pdf_hash"),
                        pdf_path,
                        json.dumps(engine) if engine else None,
                        o.get("createdAt", _now()), _now(),
                    ],
                )
                conn.execute("DELETE FROM file2edi_order_partners WHERE order_id=?", [o["orderId"]])
                conn.execute("DELETE FROM file2edi_order_lines WHERE order_id=?", [o["orderId"]])
                conn.execute("DELETE FROM file2edi_order_anomalies WHERE order_id=?", [o["orderId"]])
                for p in review.get("partners", []):
                    conn.execute(
                        """INSERT INTO file2edi_order_partners
                        (partner_id,order_id,partner_function,partner_code,partner_name,
                         address_line_1,postal_code,city,country,confidence,manually_edited,edited_fields_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        [
                            p["partnerId"], p["orderId"], p["partnerFunction"], p["partnerCode"],
                            p["partnerName"], p.get("addressLine1"), p.get("postalCode"),
                            p.get("city"), p.get("country", "FR"), p.get("confidence", 0),
                            1 if p.get("manuallyEdited") else 0,
                            json.dumps(p.get("editedFields") or {}),
                        ],
                    )
                for ln in review.get("lines", []):
                    conn.execute(
                        """INSERT INTO file2edi_order_lines
                        (line_id,order_id,line_number,customer_reference,bosch_article,designation,
                         quantity,unit,unit_price,amount,confidence,status,comment,manually_edited)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        [
                            ln["lineId"], ln["orderId"], ln["lineNumber"], ln.get("customerReference"),
                            ln.get("boschArticle"), ln.get("designation"), ln.get("quantity", 0),
                            ln.get("unit", "PCE"), ln.get("unitPrice", 0), ln.get("amount", 0),
                            ln.get("confidence", 0), ln.get("status", "OK"), ln.get("comment"),
                            1 if ln.get("manuallyEdited") else 0,
                        ],
                    )
                for a in review.get("anomalies", []):
                    conn.execute(
                        """INSERT INTO file2edi_order_anomalies
                        (anomaly_id,order_id,line_id,severity,field_name,message,status,created_at)
                        VALUES (?,?,?,?,?,?,?,?)
                        ON CONFLICT(anomaly_id) DO UPDATE SET
                          order_id=excluded.order_id,
                          line_id=excluded.line_id,
                          severity=excluded.severity,
                          field_name=excluded.field_name,
                          message=excluded.message,
                          status=excluded.status,
                          created_at=excluded.created_at""",
                        [
                            a["anomalyId"], a["orderId"], a.get("lineId"), a.get("severity"),
                            a.get("fieldName"), a["message"], a.get("status", "Ouverte"),
                            a.get("createdAt", _now()),
                        ],
                    )
                conn.commit()
            finally:
                conn.close()
            self._sync_conversion_row(review, engine)

        self._execute_write(_write)

    def _sync_conversion_row(self, review: dict, engine: dict | None) -> None:
        """Mirror into platform conversions table (Delta/JSONL/SQLite via server adapter)."""
        try:
            import server as srv  # lazy: server defines save_conversion at runtime
            o = review["order"]
            cid = o["orderId"]
            row = {
                "id": cid,
                "correlation_id": o.get("uploadId"),
                "source_filename": o.get("fileName"),
                "pdf_hash": (engine or {}).get("pdf_hash"),
                "status": "REVIEW_REQUIRED" if o.get("reviewRequired") else "COMPLETED",
                "business_status": o.get("status"),
                "po_number": o.get("customerOrderNumber"),
                "order_date": o.get("orderDate"),
                "delivery_date": o.get("requestedDeliveryDate"),
                "soldto": next((p["partnerCode"] for p in review.get("partners", []) if p["partnerFunction"] == "soldto"), None),
                "shipto": next((p["partnerCode"] for p in review.get("partners", []) if p["partnerFunction"] == "shipto"), None),
                "customer_name": o.get("clientName"),
                "confidence": int(o.get("globalConfidence") or 0),
                "line_count": o.get("lineCount", 0),
                "extraction_json": json.dumps(engine) if engine else None,
                "created_at": o.get("createdAt", _now()),
                "updated_at": _now(),
            }
            if hasattr(srv, "save_conversion"):
                srv.save_conversion(row)
        except Exception:
            pass

    def load_order_review(self, order_id: str) -> dict | None:
        conn = self._conn()
        row = conn.execute("SELECT * FROM file2edi_orders WHERE order_id=?", [order_id]).fetchone()
        if not row:
            conn.close()
            return None
        partners = [dict(r) for r in conn.execute(
            "SELECT * FROM file2edi_order_partners WHERE order_id=?", [order_id]
        ).fetchall()]
        lines = [dict(r) for r in conn.execute(
            "SELECT * FROM file2edi_order_lines WHERE order_id=? ORDER BY line_number", [order_id]
        ).fetchall()]
        anomalies = [dict(r) for r in conn.execute(
            "SELECT * FROM file2edi_order_anomalies WHERE order_id=?", [order_id]
        ).fetchall()]
        conn.close()
        return self._row_to_review(dict(row), partners, lines, anomalies)

    def _row_to_review(self, row: dict, partners: list, lines: list, anomalies: list) -> dict:
        def camel(d: dict, mapping: dict) -> dict:
            return {mapping.get(k, k): v for k, v in d.items()}

        p_map = {
            "partner_id": "partnerId", "order_id": "orderId", "partner_function": "partnerFunction",
            "partner_code": "partnerCode", "partner_name": "partnerName", "address_line_1": "addressLine1",
            "postal_code": "postalCode", "city": "city", "country": "country", "confidence": "confidence",
            "manually_edited": "manuallyEdited", "edited_fields_json": "editedFieldsJson",
        }
        l_map = {
            "line_id": "lineId", "order_id": "orderId", "line_number": "lineNumber",
            "customer_reference": "customerReference", "bosch_article": "boschArticle",
            "designation": "designation", "quantity": "quantity", "unit": "unit",
            "unit_price": "unitPrice", "amount": "amount", "confidence": "confidence",
            "status": "status", "comment": "comment", "manually_edited": "manuallyEdited",
        }
        a_map = {
            "anomaly_id": "anomalyId", "order_id": "orderId", "line_id": "lineId",
            "severity": "severity", "field_name": "fieldName", "message": "message",
            "status": "status", "created_at": "createdAt",
        }
        order = {
            "orderId": row["order_id"],
            "uploadId": row["upload_id"],
            "fileName": row["file_name"],
            "clientName": row["client_name"],
            "customerOrderNumber": row["customer_order_number"],
            "documentReference": row["document_reference"],
            "orderDate": row["order_date"],
            "requestedDeliveryDate": row["requested_delivery_date"],
            "currency": row["currency"],
            "incoterm": row["incoterm"],
            "deliveryMode": row["delivery_mode"],
            "messageType": row["message_type"],
            "vendor": row["vendor"],
            "totalAmount": row["total_amount"],
            "globalConfidence": row["global_confidence"],
            "status": row["status"],
            "reviewRequired": bool(row["review_required"]),
            "lineCount": row["line_count"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        review_required = order["globalConfidence"] < 90
        trace = [
            {"id": "1", "label": "PDF reçu", "status": "completed"},
            {"id": "2", "label": "Extraction OCR", "status": "completed"},
            {"id": "3", "label": "Mapping client", "status": "completed"},
            {"id": "4", "label": "Contrôles métier", "status": "completed"},
            {"id": "5", "label": "Revue manuelle", "status": "current" if review_required else "completed"},
            {"id": "6", "label": "Génération EDIFACT", "status": "completed" if row.get("edifact_content") else "pending"},
            {"id": "7", "label": "Export SFTP", "status": "pending"},
        ]
        return {
            "order": order,
            "partners": [self._partner_to_api(dict(p)) for p in partners],
            "lines": [camel(dict(l), l_map) for l in lines],
            "anomalies": [camel(dict(a), a_map) for a in anomalies],
            "traceability": trace,
            "edifactReady": bool(row.get("edifact_content") or row.get("edifact_filename")),
            "pdfUrl": f"/api/orders/{order['orderId']}/pdf",
        }

    def _partner_to_api(self, partner: dict) -> dict:
        raw = partner.get("edited_fields_json")
        edited_fields: dict[str, str] = {}
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    edited_fields = {
                        str(k): v
                        for k, v in parsed.items()
                        if v in ("manual", "auto")
                    }
            except json.JSONDecodeError:
                pass
        return {
            "partnerId": partner.get("partner_id"),
            "orderId": partner.get("order_id"),
            "partnerFunction": partner.get("partner_function"),
            "partnerCode": partner.get("partner_code"),
            "partnerName": partner.get("partner_name"),
            "addressLine1": partner.get("address_line_1"),
            "postalCode": partner.get("postal_code"),
            "city": partner.get("city"),
            "country": partner.get("country"),
            "confidence": partner.get("confidence"),
            "manuallyEdited": bool(partner.get("manually_edited")),
            "editedFields": edited_fields,
        }

    def list_orders_summary(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT o.order_id,
                      COALESCE(u.file_name, o.file_name) AS file_name,
                      o.client_name, o.global_confidence, o.status,
                      o.created_at, o.updated_at
               FROM file2edi_orders o
               LEFT JOIN file2edi_pdf_uploads u ON u.upload_id = o.upload_id
               ORDER BY o.created_at DESC
               LIMIT 200"""
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_order_header(self, order_id: str, payload: dict) -> dict | None:
        if not self.load_order_review(order_id):
            return None
        field_map = {
            "clientName": "client_name", "customerOrderNumber": "customer_order_number",
            "documentReference": "document_reference", "orderDate": "order_date",
            "requestedDeliveryDate": "requested_delivery_date", "currency": "currency",
            "incoterm": "incoterm", "deliveryMode": "delivery_mode",
        }
        conn = self._conn()
        sets, vals = [], []
        for k, col in field_map.items():
            if k in payload:
                sets.append(f"{col}=?")
                vals.append(payload[k])
        if sets:
            vals.append(_now())
            vals.append(order_id)
            conn.execute(
                f"UPDATE file2edi_orders SET {', '.join(sets)}, updated_at=? WHERE order_id=?",
                vals,
            )
            conn.commit()
        conn.close()
        return self.load_order_review(order_id)

    def update_partner(self, partner_id: str, payload: dict) -> dict | None:
        payload = dict(payload)
        edit_sources = payload.pop("editSources", None) or {}
        default_source = payload.pop("editSource", "manual")
        if default_source not in ("manual", "auto"):
            default_source = "manual"

        conn = self._conn()
        row = conn.execute(
            "SELECT order_id, partner_function, edited_fields_json FROM file2edi_order_partners WHERE partner_id=?",
            [partner_id],
        ).fetchone()
        if not row:
            conn.close()
            return None
        order_id = row["order_id"]
        edited_fields: dict[str, str] = {}
        if row["edited_fields_json"]:
            try:
                parsed = json.loads(row["edited_fields_json"])
                if isinstance(parsed, dict):
                    edited_fields = {
                        str(k): v for k, v in parsed.items() if v in ("manual", "auto")
                    }
            except json.JSONDecodeError:
                pass

        field_map = {
            "partnerCode": "partner_code",
            "partnerName": "partner_name",
            "addressLine1": "address_line_1",
            "postalCode": "postal_code",
            "city": "city",
            "country": "country",
        }
        sets, vals = [], []
        for key, col in field_map.items():
            if key in payload:
                source = edit_sources.get(key, default_source)
                if source not in ("manual", "auto"):
                    source = default_source
                edited_fields[key] = source
                sets.append(f"{col}=?")
                vals.append(payload[key])
        if sets:
            sets.append("edited_fields_json=?")
            vals.append(json.dumps(edited_fields))
            sets.append("manually_edited=?")
            vals.append(1 if any(v == "manual" for v in edited_fields.values()) else 0)
            vals.append(partner_id)
            conn.execute(
                f"UPDATE file2edi_order_partners SET {', '.join(sets)} WHERE partner_id=?",
                vals,
            )
            if row["partner_function"] == "shipto" and payload.get("partnerName"):
                conn.execute(
                    "UPDATE file2edi_orders SET client_name=?, updated_at=? WHERE order_id=?",
                    [payload["partnerName"], _now(), order_id],
                )
            conn.commit()
        conn.close()
        return self.load_order_review(order_id)

    def update_line(self, line_id: str, payload: dict) -> dict | None:
        conn = self._conn()
        row = conn.execute("SELECT order_id, quantity, unit_price FROM file2edi_order_lines WHERE line_id=?", [line_id]).fetchone()
        if not row:
            conn.close()
            return None
        order_id = row["order_id"]
        mapping = {
            "customerReference": "customer_reference", "boschArticle": "bosch_article",
            "designation": "designation", "quantity": "quantity", "unit": "unit",
            "unitPrice": "unit_price", "status": "status", "comment": "comment",
        }
        sets, vals = ["manually_edited=1"], []
        qty = payload.get("quantity", row["quantity"])
        price = payload.get("unitPrice", row["unit_price"])
        for k, col in mapping.items():
            if k in payload:
                sets.append(f"{col}=?")
                vals.append(payload[k])
                if k == "quantity":
                    qty = payload[k]
                if k == "unitPrice":
                    price = payload[k]
        amount = float(qty or 0) * float(price or 0)
        sets.append("amount=?")
        vals.append(amount)
        vals.append(line_id)
        conn.execute(f"UPDATE file2edi_order_lines SET {', '.join(sets)} WHERE line_id=?", vals)
        conn.commit()
        self._recalc_order_total(conn, order_id)
        conn.close()
        return self.load_order_review(order_id)

    def _recalc_order_total(self, conn: sqlite3.Connection, order_id: str) -> None:
        total = conn.execute(
            "SELECT COALESCE(SUM(amount),0), COUNT(*) FROM file2edi_order_lines WHERE order_id=?",
            [order_id],
        ).fetchone()
        conn.execute(
            "UPDATE file2edi_orders SET total_amount=?, line_count=?, updated_at=? WHERE order_id=?",
            [total[0], total[1], _now(), order_id],
        )
        conn.commit()

    def add_line(self, order_id: str, payload: dict) -> dict | None:
        conn = self._conn()
        n = conn.execute(
            "SELECT COALESCE(MAX(line_number),0)+1 FROM file2edi_order_lines WHERE order_id=?", [order_id]
        ).fetchone()[0]
        line_id = f"ln-{uuid.uuid4().hex[:8]}"
        qty = float(payload.get("quantity", 1))
        price = float(payload.get("unitPrice", 0))
        conn.execute(
            """INSERT INTO file2edi_order_lines
            (line_id,order_id,line_number,customer_reference,bosch_article,designation,
             quantity,unit,unit_price,amount,confidence,status,manually_edited)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)""",
            [
                line_id, order_id, n, payload.get("customerReference", ""),
                payload.get("boschArticle", ""), payload.get("designation", ""),
                qty, payload.get("unit", "PCE"), price, qty * price,
                100, payload.get("status", "Corrigé manuellement"),
            ],
        )
        conn.commit()
        self._recalc_order_total(conn, order_id)
        conn.close()
        return self.load_order_review(order_id)

    def delete_line(self, line_id: str) -> dict | None:
        conn = self._conn()
        row = conn.execute("SELECT order_id FROM file2edi_order_lines WHERE line_id=?", [line_id]).fetchone()
        if not row:
            conn.close()
            return None
        order_id = row["order_id"]
        conn.execute("DELETE FROM file2edi_order_lines WHERE line_id=?", [line_id])
        conn.commit()
        self._recalc_order_total(conn, order_id)
        conn.close()
        return self.load_order_review(order_id)

    def resolve_anomaly(self, anomaly_id: str, action: str) -> dict | None:
        status_map = {"corrected": "Corrigée", "ignored": "Ignorée", "blocking": "Bloquante"}
        conn = self._conn()
        row = conn.execute(
            "SELECT order_id FROM file2edi_order_anomalies WHERE anomaly_id=?", [anomaly_id]
        ).fetchone()
        if not row:
            conn.close()
            return None
        conn.execute(
            "UPDATE file2edi_order_anomalies SET status=? WHERE anomaly_id=?",
            [status_map.get(action, "Corrigée"), anomaly_id],
        )
        conn.commit()
        conn.close()
        return self.load_order_review(row["order_id"])

    def mark_edifact_generated(self, order_id: str, filename: str, content: str) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE file2edi_orders SET status='Généré', edifact_filename=?, edifact_content=?, review_required=0, updated_at=? WHERE order_id=?",
            [filename, content, _now(), order_id],
        )
        conn.execute(
            """INSERT OR REPLACE INTO file2edi_conversion_history
            (conversion_id,order_id,file_name,status,confidence,edifact_path,processed_at,processed_by)
            SELECT order_id, order_id, file_name, 'Généré', global_confidence, ?, ?, 'operator'
            FROM file2edi_orders WHERE order_id=?""",
            [filename, _now(), order_id],
        )
        conn.commit()
        conn.close()

    def get_edifact_export(self, order_id: str) -> dict | None:
        conn = self._conn()
        row = conn.execute(
            "SELECT edifact_filename, edifact_content FROM file2edi_orders WHERE order_id=?",
            [order_id],
        ).fetchone()
        conn.close()
        if not row or not row["edifact_content"]:
            return None
        return {
            "fileName": row["edifact_filename"] or f"ORDERS_{order_id}.tst",
            "content": row["edifact_content"],
        }


_store: File2EdiStore | None = None


def get_store() -> File2EdiStore:
    global _store
    if _store is None:
        import os
        from pathlib import Path
        app_root = Path(__file__).resolve().parents[2]
        db = os.environ.get(
            "FILE2EDI_DB_PATH",
            os.environ.get("DB_PATH", str(app_root / "data" / "file2edi.db")),
        )
        if db.endswith("edifact_standalone.db"):
            db = str(app_root / "data" / "file2edi.db")
        intake = os.environ.get("INTAKE_DIR", str(app_root / "data" / "intake"))
        _store = File2EdiStore(db, intake)
    return _store
