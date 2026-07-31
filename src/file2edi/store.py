"""File2EDI persistence — SQLite (+ optional Delta sync via server persistence adapter)."""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "data" / "file2edi_schema.sql"
_APP_SETTINGS_KEY = "app_settings_v1"
_log = logging.getLogger("edifact.file2edi.store")

_APP_SETTINGS_DEFAULT: dict[str, Any] = {
    "defaultIncoterm": "DAP - Delivered At Place",
    "currency": "EUR - Euro",
    "documentLanguage": "Français (FR)",
    "timezone": "(UTC+01:00) Europe/Paris",
    "connectorConfig": {
        "apiBaseUrl": "",
        "dbSyncEnabled": True,
        "csvDelimiter": ";",
        "sftpProfile": "default",
    },
    "aiProvider": "databricks",
    "databricksConfig": {
        "host": "https://adb-5555213114570927.7.azuredatabricks.net",
        "apiBaseUrl": "https://file2edi-5555213114570927.7.azure.databricksapps.com",
        "modelEndpoint": "databricks-gpt-oss-120b",
        "sqlWarehouseEnabled": False,
        "warehouseId": "",
        "catalog": "hive_metastore",
        "schema": "edifact_generator",
        "configProfile": "",
        "llmEnabled": True,
    },
    "openaiConfig": {
        "baseUrl": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
    },
    "ollamaConfig": {
        "baseUrl": "http://localhost:11434",
        "model": "llama3.1",
    },
    "customAiConfig": {
        "baseUrl": "",
        "model": "",
        "chatPath": "/v1/chat/completions",
        "authHeader": "Authorization",
        "authScheme": "Bearer",
        "customHeaders": "",
    },
    "validation": {
        "autoValidationThreshold": 90,
        "requireCustomerReference": True,
        "requireDeliveryDate": False,
        "blockOnAmountMismatch": True,
        "duplicateWindowDays": 30,
    },
    "notifications": {
        "emailEnabled": False,
        "emailRecipients": "",
        "notifyOnSuccess": False,
        "notifyOnFailure": True,
        "webhookEnabled": False,
        "webhookUrl": "",
    },
    "sftpConfig": {
        "enabled": False,
        "host": "",
        "port": 22,
        "username": "",
        "remotePath": "/inbox",
        "fileNamePattern": "ORDERS_{orderId}.edi",
        "hasPassword": False,
    },
    "security": {
        "enforceAuth": True,
        "sessionTimeoutMinutes": 480,
        "maxLoginAttempts": 5,
        "auditLogEnabled": True,
        "ipAllowlist": "",
    },
    "options": {
        "autoValidateAbove90": True,
        "detectDuplicates": True,
        "autoSftp": False,
        "manualReviewOnAnomaly": True,
        "notifyOnDuplicate": False,
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "y"}
    return False


def _merge_settings(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_settings(merged[key], value)
        else:
            merged[key] = value
    return merged


def _sanitize_settings_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("defaultIncoterm", "currency", "documentLanguage", "timezone"):
        if key in payload and payload.get(key) is not None:
            out[key] = str(payload.get(key)).strip()

    raw_connector = payload.get("connectorConfig")
    if isinstance(raw_connector, dict):
        connector: dict[str, Any] = {}
        if "apiBaseUrl" in raw_connector:
            connector["apiBaseUrl"] = str(raw_connector.get("apiBaseUrl") or "").strip()
        if "dbSyncEnabled" in raw_connector:
            connector["dbSyncEnabled"] = _as_bool(raw_connector.get("dbSyncEnabled"))
        if "csvDelimiter" in raw_connector:
            val = str(raw_connector.get("csvDelimiter") or ";").strip()
            connector["csvDelimiter"] = val[0] if val else ";"
        if "sftpProfile" in raw_connector:
            connector["sftpProfile"] = str(raw_connector.get("sftpProfile") or "default").strip() or "default"
        if connector:
            out["connectorConfig"] = connector

    raw_databricks = payload.get("databricksConfig")
    if isinstance(raw_databricks, dict):
        databricks: dict[str, Any] = {}
        for key in (
            "host",
            "apiBaseUrl",
            "modelEndpoint",
            "warehouseId",
            "catalog",
            "schema",
            "configProfile",
        ):
            if key in raw_databricks:
                databricks[key] = str(raw_databricks.get(key) or "").strip()
        if "sqlWarehouseEnabled" in raw_databricks:
            databricks["sqlWarehouseEnabled"] = _as_bool(raw_databricks.get("sqlWarehouseEnabled"))
        if "llmEnabled" in raw_databricks:
            databricks["llmEnabled"] = _as_bool(raw_databricks.get("llmEnabled"))
        if databricks:
            out["databricksConfig"] = databricks

    ai_provider = payload.get("aiProvider")
    if ai_provider is not None:
        provider = str(ai_provider).strip().lower()
        allowed = {"databricks", "openai", "ollama", "custom"}
        out["aiProvider"] = provider if provider in allowed else "databricks"

    raw_openai = payload.get("openaiConfig")
    if isinstance(raw_openai, dict):
        openai_cfg: dict[str, Any] = {}
        for key in ("baseUrl", "model"):
            if key in raw_openai:
                openai_cfg[key] = str(raw_openai.get(key) or "").strip()
        if openai_cfg:
            out["openaiConfig"] = openai_cfg

    raw_ollama = payload.get("ollamaConfig")
    if isinstance(raw_ollama, dict):
        ollama_cfg: dict[str, Any] = {}
        for key in ("baseUrl", "model"):
            if key in raw_ollama:
                ollama_cfg[key] = str(raw_ollama.get(key) or "").strip()
        if ollama_cfg:
            out["ollamaConfig"] = ollama_cfg

    raw_custom = payload.get("customAiConfig")
    if isinstance(raw_custom, dict):
        custom_cfg: dict[str, Any] = {}
        for key in ("baseUrl", "model", "chatPath", "authHeader", "authScheme", "customHeaders"):
            if key in raw_custom:
                custom_cfg[key] = str(raw_custom.get(key) or "").strip()
        if custom_cfg:
            out["customAiConfig"] = custom_cfg

    raw_validation = payload.get("validation")
    if isinstance(raw_validation, dict):
        validation: dict[str, Any] = {}
        if "autoValidationThreshold" in raw_validation:
            try:
                val = int(raw_validation.get("autoValidationThreshold"))
            except (TypeError, ValueError):
                val = 90
            validation["autoValidationThreshold"] = max(0, min(100, val))
        if "requireCustomerReference" in raw_validation:
            validation["requireCustomerReference"] = _as_bool(raw_validation.get("requireCustomerReference"))
        if "requireDeliveryDate" in raw_validation:
            validation["requireDeliveryDate"] = _as_bool(raw_validation.get("requireDeliveryDate"))
        if "blockOnAmountMismatch" in raw_validation:
            validation["blockOnAmountMismatch"] = _as_bool(raw_validation.get("blockOnAmountMismatch"))
        if "duplicateWindowDays" in raw_validation:
            try:
                days = int(raw_validation.get("duplicateWindowDays"))
            except (TypeError, ValueError):
                days = 30
            validation["duplicateWindowDays"] = max(1, min(365, days))
        if validation:
            out["validation"] = validation

    raw_notifications = payload.get("notifications")
    if isinstance(raw_notifications, dict):
        notifications: dict[str, Any] = {}
        for key in ("emailEnabled", "notifyOnSuccess", "notifyOnFailure", "webhookEnabled"):
            if key in raw_notifications:
                notifications[key] = _as_bool(raw_notifications.get(key))
        if "emailRecipients" in raw_notifications:
            notifications["emailRecipients"] = str(raw_notifications.get("emailRecipients") or "").strip()
        if "webhookUrl" in raw_notifications:
            notifications["webhookUrl"] = str(raw_notifications.get("webhookUrl") or "").strip()
        if notifications:
            out["notifications"] = notifications

    raw_sftp = payload.get("sftpConfig")
    if isinstance(raw_sftp, dict):
        sftp: dict[str, Any] = {}
        if "enabled" in raw_sftp:
            sftp["enabled"] = _as_bool(raw_sftp.get("enabled"))
        for key in ("host", "username", "remotePath", "fileNamePattern"):
            if key in raw_sftp:
                sftp[key] = str(raw_sftp.get(key) or "").strip()
        if "port" in raw_sftp:
            try:
                port = int(raw_sftp.get("port"))
            except (TypeError, ValueError):
                port = 22
            sftp["port"] = max(1, min(65535, port))
        if sftp:
            out["sftpConfig"] = sftp

    raw_security = payload.get("security")
    if isinstance(raw_security, dict):
        security: dict[str, Any] = {}
        if "enforceAuth" in raw_security:
            security["enforceAuth"] = _as_bool(raw_security.get("enforceAuth"))
        if "auditLogEnabled" in raw_security:
            security["auditLogEnabled"] = _as_bool(raw_security.get("auditLogEnabled"))
        if "sessionTimeoutMinutes" in raw_security:
            try:
                ttl = int(raw_security.get("sessionTimeoutMinutes"))
            except (TypeError, ValueError):
                ttl = 480
            security["sessionTimeoutMinutes"] = max(15, min(1440, ttl))
        if "maxLoginAttempts" in raw_security:
            try:
                attempts = int(raw_security.get("maxLoginAttempts"))
            except (TypeError, ValueError):
                attempts = 5
            security["maxLoginAttempts"] = max(1, min(20, attempts))
        if "ipAllowlist" in raw_security:
            security["ipAllowlist"] = str(raw_security.get("ipAllowlist") or "").strip()
        if security:
            out["security"] = security

    raw_options = payload.get("options")
    if isinstance(raw_options, dict):
        opts: dict[str, bool] = {}
        for key in (
            "autoValidateAbove90",
            "detectDuplicates",
            "autoSftp",
            "manualReviewOnAnomaly",
            "notifyOnDuplicate",
        ):
            if key in raw_options:
                opts[key] = _as_bool(raw_options.get(key))
        if opts:
            out["options"] = opts
    return out


class File2EdiStore:
    def __init__(self, db_path: str, intake_dir: str) -> None:
        self.db_path = db_path
        requested_intake = Path(intake_dir)
        try:
            requested_intake.mkdir(parents=True, exist_ok=True)
            self.intake_dir = requested_intake
        except (PermissionError, OSError):
            app_root = Path(__file__).resolve().parents[2]
            local_intake = app_root / "data" / "intake"
            local_intake.mkdir(parents=True, exist_ok=True)
            self.intake_dir = local_intake
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

        def _ensure_column(table: str, column: str, ddl: str) -> None:
            cols = {
                r[1]
                for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if column not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

        # Legacy Databricks DBs can keep an older schema if the table already
        # existed; add missing columns incrementally to keep reads/writes safe.
        _ensure_column("file2edi_order_partners", "edited_fields_json", "edited_fields_json TEXT")

        _ensure_column("file2edi_orders", "upload_id", "upload_id TEXT")
        _ensure_column("file2edi_orders", "file_name", "file_name TEXT")
        _ensure_column("file2edi_orders", "client_name", "client_name TEXT")
        _ensure_column("file2edi_orders", "global_confidence", "global_confidence REAL DEFAULT 0")
        _ensure_column("file2edi_orders", "status", "status TEXT DEFAULT 'Revue requise'")
        _ensure_column("file2edi_orders", "created_at", "created_at TEXT")
        _ensure_column("file2edi_orders", "updated_at", "updated_at TEXT")
        _ensure_column("file2edi_orders", "source", "source TEXT DEFAULT 'unknown'")

        _ensure_column("file2edi_pdf_uploads", "file_name", "file_name TEXT")

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
                      uploaded_at=excluded.uploaded_at,
                      uploaded_by=excluded.uploaded_by""",
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
            "SELECT upload_id, file_name, file_size, file_path, uploaded_at, uploaded_by, status"
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

    def save_order_review(self, review: dict, sync_delta: bool = True) -> None:
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
                      total_amount,global_confidence,status,review_required,line_count,pdf_hash,pdf_path,source,
                      extraction_json,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                      source=excluded.source,
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
                        str(o.get("source") or "unknown"),
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
                         quantity,unit,unit_price,amount,confidence,status,comment,manually_edited,
                         payment_terms,delivery_date,special_instructions,warnings)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        [
                            ln["lineId"], ln["orderId"], ln["lineNumber"], ln.get("customerReference"),
                            ln.get("boschArticle"), ln.get("designation"), ln.get("quantity", 0),
                            ln.get("unit", "PCE"), ln.get("unitPrice", 0), ln.get("amount", 0),
                            ln.get("confidence", 0), ln.get("status", "OK"), ln.get("comment"),
                            1 if ln.get("manuallyEdited") else 0,
                            ln.get("paymentTerms"), ln.get("deliveryDate"),
                            ln.get("specialInstructions"), ln.get("warnings"),
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
            if sync_delta:
                self._sync_order_graph(review)

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
        except Exception as exc:
            _log.warning("conversion mirror failed for order %s: %s",
                         review.get("order", {}).get("orderId"), exc)

    def _sync_order_graph(self, review: dict | None) -> None:
        """Mirror the full order graph into Delta (best-effort, via server adapter)."""
        if not review:
            return
        try:
            import server as srv  # lazy: Delta adapter lives in server
            if hasattr(srv, "save_order_graph"):
                srv.save_order_graph(review)
        except Exception as exc:
            _log.warning("delta order-graph sync failed for order %s: %s",
                         review.get("order", {}).get("orderId"), exc)

    def hydrate_from_delta(self) -> int:
        """Rebuild the local SQLite order cache from Delta on startup.

        Only runs when the Delta backend is active AND the local order table is
        empty (i.e. a fresh/ephemeral container). Writes are sync-free to avoid
        mirroring straight back to Delta. Returns the number of orders loaded.
        """
        try:
            import server as srv  # lazy
            if not hasattr(srv, "load_order_graphs_from_delta"):
                return 0
            conn = self._conn()
            existing = conn.execute("SELECT COUNT(*) FROM file2edi_orders").fetchone()[0]
            conn.close()
            if existing > 0:
                return 0
            reviews = srv.load_order_graphs_from_delta()
            count = 0
            for rev in reviews:
                try:
                    self.save_order_review(rev, sync_delta=False)
                    count += 1
                except Exception as exc:
                    _log.warning("hydrate: skip order %s: %s",
                                 rev.get("order", {}).get("orderId"), exc)
            if count:
                _log.info("hydrate: loaded %d orders from Delta into local SQLite", count)
            return count
        except Exception as exc:
            _log.warning("hydrate_from_delta failed: %s", exc)
            return 0


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
            "payment_terms": "paymentTerms", "delivery_date": "deliveryDate",
            "special_instructions": "specialInstructions", "warnings": "warnings",
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
            "source": row.get("source") or "unknown",
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
                      o.source,
                      o.created_at, o.updated_at,
                      h.processed_at, h.processed_by
               FROM file2edi_orders o
               LEFT JOIN file2edi_pdf_uploads u ON u.upload_id = o.upload_id
               LEFT JOIN file2edi_conversion_history h ON h.order_id = o.order_id
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
        review = self.load_order_review(order_id)
        self._sync_order_graph(review)
        return review

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
        review = self.load_order_review(order_id)
        self._sync_order_graph(review)
        return review

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
        review = self.load_order_review(order_id)
        self._sync_order_graph(review)
        return review

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
             quantity,unit,unit_price,amount,confidence,status,manually_edited,
             payment_terms,delivery_date,special_instructions,warnings)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)""",
            [
                line_id, order_id, n, payload.get("customerReference", ""),
                payload.get("boschArticle", ""), payload.get("designation", ""),
                qty, payload.get("unit", "PCE"), price, qty * price,
                100, payload.get("status", "Corrigé manuellement"),
                payload.get("paymentTerms"), payload.get("deliveryDate"),
                payload.get("specialInstructions"), payload.get("warnings"),
            ],
        )
        conn.commit()
        self._recalc_order_total(conn, order_id)
        conn.close()
        review = self.load_order_review(order_id)
        self._sync_order_graph(review)
        return review

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
        review = self.load_order_review(order_id)
        self._sync_order_graph(review)
        return review

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
        review = self.load_order_review(row["order_id"])
        self._sync_order_graph(review)
        return review

    def mark_edifact_generated(self, order_id: str, filename: str, content: str, actor: str = "operator") -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE file2edi_orders SET status='Généré', edifact_filename=?, edifact_content=?, review_required=0, updated_at=? WHERE order_id=?",
            [filename, content, _now(), order_id],
        )
        conn.execute(
            """INSERT OR REPLACE INTO file2edi_conversion_history
            (conversion_id,order_id,file_name,status,confidence,edifact_path,processed_at,processed_by)
            SELECT order_id, order_id, file_name, 'Généré', global_confidence, ?, ?, ?
            FROM file2edi_orders WHERE order_id=?""",
            [filename, _now(), actor or "operator", order_id],
        )
        conn.commit()
        conn.close()
        self._sync_order_graph(self.load_order_review(order_id))

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

    def load_app_settings(self) -> dict[str, Any]:
        conn = self._conn()
        row = conn.execute(
            "SELECT setting_value FROM file2edi_settings WHERE setting_key=?",
            [_APP_SETTINGS_KEY],
        ).fetchone()
        conn.close()
        if not row:
            return dict(_APP_SETTINGS_DEFAULT)
        try:
            parsed = json.loads(row["setting_value"] or "{}")
            if not isinstance(parsed, dict):
                return dict(_APP_SETTINGS_DEFAULT)
            sanitized = _sanitize_settings_payload(parsed)
            return _merge_settings(_APP_SETTINGS_DEFAULT, sanitized)
        except Exception:
            return dict(_APP_SETTINGS_DEFAULT)

    def save_app_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.load_app_settings()
        sanitized = _sanitize_settings_payload(payload)
        merged = _merge_settings(current, sanitized)

        def _write() -> dict[str, Any]:
            conn = self._conn()
            try:
                conn.execute(
                    """INSERT INTO file2edi_settings (setting_key, setting_value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(setting_key) DO UPDATE SET
                      setting_value=excluded.setting_value,
                      updated_at=excluded.updated_at""",
                    [_APP_SETTINGS_KEY, json.dumps(merged), _now()],
                )
                conn.commit()
            finally:
                conn.close()
            return merged

        return self._execute_write(_write)


class _PostgresCursor:
    """Tiny DB-API compatibility wrapper around psycopg cursors.

    The SQLite store uses ``?`` placeholders everywhere.  Translating them here
    lets the Postgres store reuse the battle-tested File2EdiStore methods while
    keeping the backend selection isolated.
    """

    def __init__(self, cursor) -> None:
        self._cursor = cursor

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class _PostgresConnection:
    def __init__(self, conn) -> None:
        self._conn = conn

    def execute(self, sql: str, params: list | tuple | None = None) -> _PostgresCursor:
        stripped = sql.strip().upper()
        if stripped.startswith("PRAGMA"):
            return _PostgresCursor(self._conn.cursor())
        translated = sql.replace("?", "%s")
        return _PostgresCursor(self._conn.execute(translated, params or []))

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


class PostgresFile2EdiStore(File2EdiStore):
    """PostgreSQL-backed implementation of the File2EDI store contract."""

    def __init__(self, database_url: str, intake_dir: str) -> None:
        self.database_url = _normalize_postgres_url(database_url)
        self.db_path = self.database_url
        requested_intake = Path(intake_dir)
        try:
            requested_intake.mkdir(parents=True, exist_ok=True)
            self.intake_dir = requested_intake
        except (PermissionError, OSError):
            app_root = Path(__file__).resolve().parents[2]
            local_intake = app_root / "data" / "intake"
            local_intake.mkdir(parents=True, exist_ok=True)
            self.intake_dir = local_intake
        self._init_schema()

    def _conn(self) -> _PostgresConnection:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL support requires psycopg. Install requirements-postgres.txt."
            ) from exc
        return _PostgresConnection(psycopg.connect(self.database_url, row_factory=dict_row))

    def _execute_write(self, fn):
        return fn()

    def _init_schema(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS file2edi_pdf_uploads (
          upload_id     TEXT PRIMARY KEY,
          file_name     TEXT NOT NULL,
          file_size     INTEGER NOT NULL,
          file_path     TEXT NOT NULL,
          uploaded_at   TEXT NOT NULL,
          uploaded_by   TEXT DEFAULT 'operator',
          status        TEXT DEFAULT 'RECEIVED'
        );

        CREATE TABLE IF NOT EXISTS file2edi_orders (
          order_id                  TEXT PRIMARY KEY,
          upload_id                 TEXT,
          file_name                 TEXT,
          client_name               TEXT,
          customer_order_number     TEXT,
          document_reference        TEXT,
          order_date                TEXT,
          requested_delivery_date   TEXT,
          currency                  TEXT DEFAULT 'EUR',
          incoterm                  TEXT DEFAULT 'DAP',
          delivery_mode             TEXT,
          message_type              TEXT DEFAULT 'ORDERS',
          vendor                    TEXT,
          total_amount              DOUBLE PRECISION DEFAULT 0,
          global_confidence         DOUBLE PRECISION DEFAULT 0,
          status                    TEXT DEFAULT 'Revue requise',
          review_required           INTEGER DEFAULT 1,
          line_count                INTEGER DEFAULT 0,
          pdf_hash                  TEXT,
          pdf_path                  TEXT,
          source                    TEXT DEFAULT 'unknown',
          edifact_content           TEXT,
          edifact_filename          TEXT,
          extraction_json           TEXT,
          corrections_json          TEXT,
          processed_by              TEXT,
          soldto                    TEXT,
          uploaded_by               TEXT DEFAULT 'operator',
          created_at                TEXT NOT NULL,
          updated_at                TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_f2e_orders_status ON file2edi_orders(status);
        CREATE INDEX IF NOT EXISTS idx_f2e_orders_upload ON file2edi_orders(upload_id);

        CREATE TABLE IF NOT EXISTS file2edi_order_partners (
          partner_id         TEXT PRIMARY KEY,
          order_id           TEXT NOT NULL REFERENCES file2edi_orders(order_id) ON DELETE CASCADE,
          partner_function   TEXT NOT NULL,
          partner_code       TEXT,
          partner_name       TEXT,
          address_line_1     TEXT,
          address_line_2     TEXT,
          postal_code        TEXT,
          city               TEXT,
          country            TEXT DEFAULT 'FR',
          confidence         DOUBLE PRECISION DEFAULT 0,
          manually_edited    INTEGER DEFAULT 0,
          edited_fields_json TEXT,
          previous_value     TEXT
        );

        CREATE TABLE IF NOT EXISTS file2edi_order_lines (
          line_id              TEXT PRIMARY KEY,
          order_id             TEXT NOT NULL REFERENCES file2edi_orders(order_id) ON DELETE CASCADE,
          line_number          INTEGER NOT NULL,
          customer_reference   TEXT,
          bosch_article        TEXT,
          designation          TEXT,
          quantity             DOUBLE PRECISION DEFAULT 0,
          unit                 TEXT DEFAULT 'PCE',
          unit_price           DOUBLE PRECISION DEFAULT 0,
          amount               DOUBLE PRECISION DEFAULT 0,
          confidence           DOUBLE PRECISION DEFAULT 0,
          status               TEXT DEFAULT 'OK',
          comment              TEXT,
          manually_edited      INTEGER DEFAULT 0,
          payment_terms        TEXT,
          delivery_date        TEXT,
          special_instructions TEXT,
          warnings             TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_f2e_lines_order ON file2edi_order_lines(order_id);

        CREATE TABLE IF NOT EXISTS file2edi_order_anomalies (
          anomaly_id TEXT PRIMARY KEY,
          order_id   TEXT NOT NULL REFERENCES file2edi_orders(order_id) ON DELETE CASCADE,
          line_id    TEXT,
          severity   TEXT DEFAULT 'warning',
          field_name TEXT,
          message    TEXT NOT NULL,
          status     TEXT DEFAULT 'Ouverte',
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS file2edi_conversion_history (
          conversion_id TEXT PRIMARY KEY,
          order_id      TEXT NOT NULL REFERENCES file2edi_orders(order_id) ON DELETE CASCADE,
          file_name     TEXT,
          status        TEXT,
          confidence    DOUBLE PRECISION,
          edifact_path  TEXT,
          processed_at  TEXT NOT NULL,
          processed_by  TEXT DEFAULT 'system'
        );

        CREATE TABLE IF NOT EXISTS file2edi_settings (
          setting_key   TEXT PRIMARY KEY,
          setting_value TEXT NOT NULL,
          updated_at    TEXT NOT NULL
        );
        """
        conn = self._conn()
        try:
            for statement in [s.strip() for s in ddl.split(";") if s.strip()]:
                conn.execute(statement)
            # Databases created by the earlier SQLAlchemy migration may already
            # have these tables but miss newer File2EDI UI columns. Keep startup
            # self-healing so migration order does not matter.
            for statement in (
                "ALTER TABLE file2edi_pdf_uploads ALTER COLUMN upload_id TYPE TEXT",
                "ALTER TABLE file2edi_orders ALTER COLUMN order_id TYPE TEXT",
                "ALTER TABLE file2edi_orders ALTER COLUMN upload_id TYPE TEXT",
                "ALTER TABLE file2edi_order_partners ALTER COLUMN partner_id TYPE TEXT",
                "ALTER TABLE file2edi_order_partners ALTER COLUMN order_id TYPE TEXT",
                "ALTER TABLE file2edi_order_lines ALTER COLUMN line_id TYPE TEXT",
                "ALTER TABLE file2edi_order_lines ALTER COLUMN order_id TYPE TEXT",
                "ALTER TABLE file2edi_order_anomalies ALTER COLUMN anomaly_id TYPE TEXT",
                "ALTER TABLE file2edi_order_anomalies ALTER COLUMN order_id TYPE TEXT",
                "ALTER TABLE file2edi_conversion_history ALTER COLUMN conversion_id TYPE TEXT",
                "ALTER TABLE file2edi_conversion_history ALTER COLUMN order_id TYPE TEXT",
                "ALTER TABLE file2edi_orders ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'unknown'",
                "ALTER TABLE file2edi_orders ADD COLUMN IF NOT EXISTS edifact_content TEXT",
                "ALTER TABLE file2edi_orders ADD COLUMN IF NOT EXISTS edifact_filename TEXT",
                "ALTER TABLE file2edi_orders ADD COLUMN IF NOT EXISTS extraction_json TEXT",
                "ALTER TABLE file2edi_orders ADD COLUMN IF NOT EXISTS corrections_json TEXT",
                "ALTER TABLE file2edi_orders ADD COLUMN IF NOT EXISTS processed_by TEXT",
                "ALTER TABLE file2edi_orders ADD COLUMN IF NOT EXISTS soldto TEXT",
                "ALTER TABLE file2edi_orders ADD COLUMN IF NOT EXISTS uploaded_by TEXT DEFAULT 'operator'",
                "ALTER TABLE file2edi_orders ALTER COLUMN uploaded_by SET DEFAULT 'operator'",
                "UPDATE file2edi_orders SET uploaded_by='operator' WHERE uploaded_by IS NULL",
                "ALTER TABLE file2edi_orders ALTER COLUMN uploaded_by SET NOT NULL",
                "ALTER TABLE file2edi_order_lines ADD COLUMN IF NOT EXISTS payment_terms TEXT",
                "ALTER TABLE file2edi_order_lines ADD COLUMN IF NOT EXISTS delivery_date TEXT",
                "ALTER TABLE file2edi_order_lines ADD COLUMN IF NOT EXISTS special_instructions TEXT",
                "ALTER TABLE file2edi_order_lines ADD COLUMN IF NOT EXISTS warnings TEXT",
                "ALTER TABLE file2edi_order_partners ADD COLUMN IF NOT EXISTS edited_fields_json TEXT",
                "ALTER TABLE file2edi_order_partners ADD COLUMN IF NOT EXISTS previous_value TEXT",
            ):
                conn.execute(statement)
            conn.commit()
        finally:
            conn.close()

    def _recalc_order_total(self, conn: _PostgresConnection, order_id: str) -> None:
        total = conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS total_amount, COUNT(*) AS line_count "
            "FROM file2edi_order_lines WHERE order_id=?",
            [order_id],
        ).fetchone()
        conn.execute(
            "UPDATE file2edi_orders SET total_amount=?, line_count=?, updated_at=? WHERE order_id=?",
            [total["total_amount"], total["line_count"], _now(), order_id],
        )
        conn.commit()

    def mark_edifact_generated(self, order_id: str, filename: str, content: str, actor: str = "operator") -> None:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE file2edi_orders SET status='Généré', edifact_filename=?, "
                "edifact_content=?, review_required=0, updated_at=? WHERE order_id=?",
                [filename, content, _now(), order_id],
            )
            conn.execute(
                """INSERT INTO file2edi_conversion_history
                (conversion_id,order_id,file_name,status,confidence,edifact_path,processed_at,processed_by)
                SELECT order_id, order_id, file_name, 'Généré', global_confidence, ?, ?, ?
                FROM file2edi_orders WHERE order_id=?
                ON CONFLICT(conversion_id) DO UPDATE SET
                  file_name=excluded.file_name,
                  status=excluded.status,
                  confidence=excluded.confidence,
                  edifact_path=excluded.edifact_path,
                  processed_at=excluded.processed_at,
                  processed_by=excluded.processed_by""",
                [filename, _now(), actor or "operator", order_id],
            )
            conn.commit()
        finally:
            conn.close()
        self._sync_order_graph(self.load_order_review(order_id))


def _normalize_postgres_url(database_url: str) -> str:
    """Accept SQLAlchemy-style PostgreSQL URLs as psycopg connection URLs."""
    if database_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + database_url.split("://", 1)[1]
    if database_url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + database_url.split("://", 1)[1]
    parsed = urlsplit(database_url)
    if parsed.scheme == "postgres":
        return urlunsplit(("postgresql", parsed.netloc, parsed.path, parsed.query, parsed.fragment))
    return database_url


_store: File2EdiStore | None = None


def get_store() -> File2EdiStore:
    global _store
    if _store is None:
        import os
        from pathlib import Path
        app_root = Path(__file__).resolve().parents[2]
        pg_url = (os.environ.get("PG_DATABASE_URL") or "").strip()
        intake = os.environ.get("INTAKE_DIR", str(app_root / "data" / "intake"))
        if pg_url:
            try:
                _store = PostgresFile2EdiStore(pg_url, intake)
                _log.info("File2EDI store backend: PostgreSQL")
                return _store
            except Exception as exc:
                if os.environ.get("FILE2EDI_POSTGRES_STRICT", "false").strip().lower() in {"1", "true", "yes", "on"}:
                    raise
                _log.warning("PostgreSQL store unavailable, falling back to SQLite: %s", exc)
        db = os.environ.get(
            "FILE2EDI_DB_PATH",
            os.environ.get("DB_PATH", str(app_root / "data" / "file2edi.db")),
        )
        if db.endswith("edifact_standalone.db"):
            db = str(app_root / "data" / "file2edi.db")
        _store = File2EdiStore(db, intake)
        _log.info("File2EDI store backend: SQLite at %s", db)
    return _store
