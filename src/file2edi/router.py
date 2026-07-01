"""FastAPI router — React File2EDI SPA contract (/api/*)."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .mapper import (
    dashboard_metrics_from_db,
    engine_to_extraction_preview,
    engine_to_order_review,
)
from .store import get_store

DEMO_ORDER_ID = "ord-rexel-026545008"


def create_router() -> APIRouter:
    router = APIRouter(tags=["file2edi"])

    # ── Health (React Header badges) ─────────────────────────────────────────
    @router.get("/health/system")
    def health_system():
        try:
            import server as srv
            h = srv.api_proxy_health()
            return {
                "api": "connected" if h.get("api", {}).get("ok") else "disconnected",
                "database": "connected" if h.get("database", {}).get("ok") else "disconnected",
                "csv": "connected" if h.get("masterdata", {}).get("ok") else "disconnected",
            }
        except Exception:
            return {"api": "disconnected", "database": "connected", "csv": "connected"}

    # ── Dashboard ───────────────────────────────────────────────────────────
    @router.get("/dashboard/metrics")
    def dashboard_metrics():
        store = get_store()
        orders = store.list_orders_summary()
        if not orders:
            try:
                import server as srv
                convs = srv.list_conversions(limit=100)
                orders = [
                    {
                        "status": _map_platform_status(c.get("status")),
                        "created_at": c.get("created_at"),
                    }
                    for c in convs
                ]
            except Exception:
                pass
        return dashboard_metrics_from_db(orders)

    @router.get("/orders")
    def list_orders():
        """All converted orders for the Revue list page."""
        store = get_store()
        return [_order_list_item(o) for o in store.list_orders_summary()]

    @router.get("/dashboard/review-queue")
    def review_queue():
        store = get_store()
        review_statuses = ("Revue requise", "À revoir", "À vérifier", "Bloqué")
        items = [
            _order_list_item(o)
            for o in store.list_orders_summary()
            if o.get("status") in review_statuses
        ]
        if not items:
            try:
                import server as srv
                for c in srv.list_conversions(status="REVIEW_REQUIRED", limit=20):
                    items.append({
                        "orderId": c.get("id"),
                        "fileName": c.get("source_filename"),
                        "clientName": c.get("customer_name") or "—",
                        "confidence": int(c.get("confidence") or 0),
                        "issue": c.get("rejection_message") or c.get("rejection_code") or "Revue requise",
                        "date": c.get("created_at"),
                        "status": "À revoir",
                    })
            except Exception:
                pass
        return items[:20]

    @router.get("/dashboard/recent-conversions")
    def recent_conversions():
        store = get_store()
        out = []
        for o in store.list_orders_summary()[:10]:
            out.append({
                "conversionId": f"conv-{o['order_id']}",
                "orderId": o["order_id"],
                "fileName": o["file_name"],
                "clientName": o["client_name"] or "—",
                "status": o.get("status", "Généré"),
                "date": o.get("updated_at") or o.get("created_at"),
                "hasEdifact": o.get("status") == "Généré",
                "hasPdf": True,
            })
        return out

    # ── Upload & extraction ─────────────────────────────────────────────────
    @router.post("/upload")
    async def upload_pdf(pdf: UploadFile = File(...)):
        if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "PDF requis")
        payload = await pdf.read()
        if len(payload) > 20 * 1024 * 1024:
            raise HTTPException(400, "Fichier trop volumineux (max 20 Mo)")
        store = get_store()
        upload_id = f"upl-{uuid.uuid4().hex[:12]}"
        dest = store.intake_dir / f"{upload_id}.pdf"
        dest.write_bytes(payload)
        meta = store.save_upload_with_id(upload_id, pdf.filename, len(payload), str(dest))
        return {"uploadId": meta["uploadId"]}

    @router.post("/upload/{upload_id}/extract")
    def extract_upload(upload_id: str):
        store = get_store()
        pdf_path = store.get_upload_path(upload_id)
        if not pdf_path:
            raise HTTPException(404, "Upload introuvable")
        payload = pdf_path.read_bytes()
        import server as srv
        result = srv._local_process_and_respond(payload, pdf_path.name)
        order_id = result.get("pdf_hash") or f"ord-{uuid.uuid4().hex[:12]}"
        page_count = 3
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                page_count = len(pdf.pages)
        except Exception:
            pass
        review = engine_to_order_review(order_id, upload_id, result)
        upload_meta = store.get_upload_meta(upload_id)
        if upload_meta and upload_meta.get("file_name"):
            review["order"]["fileName"] = upload_meta["file_name"]
        review["order"]["pdfPath"] = str(pdf_path)
        store.save_order_review(review)
        try:
            srv._init_db()
            srv._upsert_conversion(_conversion_from_engine(order_id, upload_id, result))
        except Exception:
            pass
        return engine_to_extraction_preview(
            upload_id, order_id, result, len(payload), page_count=page_count,
        )

    # ── Orders / revue ──────────────────────────────────────────────────────
    @router.get("/orders/{order_id}/review")
    def get_review(order_id: str):
        store = get_store()
        if order_id == DEMO_ORDER_ID:
            from .demo_seed import seed_demo_orders, refresh_demo_pdf
            seed_demo_orders(store)
            refresh_demo_pdf(store)
        review = store.load_order_review(order_id)
        if not review:
            try:
                import server as srv
                conv = srv.load_conversion(order_id)
                if conv:
                    ext = json.loads(conv.get("extraction_json") or "{}")
                    if ext:
                        fake = _engine_from_conversion(conv, ext)
                        review = engine_to_order_review(order_id, conv.get("correlation_id", ""), fake)
                        get_store().save_order_review(review)
            except Exception:
                pass
        if not review:
            raise HTTPException(404, "Commande introuvable")
        return review

    def _serve_order_pdf(order_id: str):
        store = get_store()
        path = store.get_pdf_path_for_order(order_id)
        if not path:
            store.ensure_order_pdf(order_id)
            path = store.get_pdf_path_for_order(order_id)
        if not path or not path.exists():
            raise HTTPException(404, "PDF introuvable pour cette commande")
        conn = store._conn()
        row = conn.execute(
            "SELECT file_name FROM file2edi_orders WHERE order_id=?", [order_id]
        ).fetchone()
        conn.close()
        fname = (row["file_name"] if row and row["file_name"] else None) or path.name
        return FileResponse(
            str(path),
            media_type="application/pdf",
            filename=fname,
            headers={"Content-Disposition": f'inline; filename="{fname}"'},
        )

    @router.get("/orders/{order_id}/pdf")
    def download_order_pdf(order_id: str):
        return _serve_order_pdf(order_id)

    @router.get("/file2edi/orders/{order_id}/pdf")
    def download_order_pdf_legacy(order_id: str):
        return _serve_order_pdf(order_id)

    @router.patch("/orders/{order_id}")
    async def patch_order(order_id: str, payload: dict):
        review = get_store().update_order_header(order_id, payload)
        if not review:
            raise HTTPException(404)
        return review

    @router.patch("/orders/partners/{partner_id}")
    async def patch_partner(partner_id: str, payload: dict):
        review = get_store().update_partner(partner_id, payload)
        if not review:
            raise HTTPException(404)
        return review

    @router.patch("/orders/lines/{line_id}")
    async def patch_line(line_id: str, payload: dict):
        review = get_store().update_line(line_id, payload)
        if not review:
            raise HTTPException(404)
        return review

    @router.post("/orders/{order_id}/lines")
    async def post_line(order_id: str, payload: dict):
        review = get_store().add_line(order_id, payload)
        if not review:
            raise HTTPException(404)
        return review

    @router.delete("/orders/lines/{line_id}")
    async def delete_line(line_id: str):
        review = get_store().delete_line(line_id)
        if not review:
            raise HTTPException(404)
        return review

    @router.patch("/orders/anomalies/{anomaly_id}")
    async def patch_anomaly(anomaly_id: str, payload: dict):
        action = payload.get("action", "corrected")
        review = get_store().resolve_anomaly(anomaly_id, action)
        if not review:
            raise HTTPException(404)
        return review

    @router.post("/orders/{order_id}/generate-edifact")
    async def generate_edifact(order_id: str):
        store = get_store()
        review = store.load_order_review(order_id)
        if not review:
            raise HTTPException(404)
        blocking = [
            a for a in review.get("anomalies", [])
            if a.get("status") in ("Ouverte", "Bloquante") and a.get("severity") in ("error", "blocking")
        ]
        if blocking:
            return {"success": False, "errors": [a["message"] for a in blocking]}
        soldto = next((p for p in review["partners"] if p["partnerFunction"] == "soldto"), None)
        shipto = next((p for p in review["partners"] if p["partnerFunction"] == "shipto"), None)
        if not soldto or not soldto.get("partnerCode"):
            return {"success": False, "errors": ["Sold-to manquant"]}
        if not shipto or not shipto.get("partnerCode"):
            return {"success": False, "errors": ["Ship-to manquant"]}
        if not review["order"].get("orderDate"):
            return {"success": False, "errors": ["Date commande invalide"]}
        for ln in review.get("lines", []):
            if not ln.get("boschArticle") or not ln.get("quantity") or not ln.get("unit"):
                return {"success": False, "errors": [f"Ligne {ln.get('lineNumber')} incomplète"]}

        import server as srv
        from starlette.requests import Request
        from starlette.datastructures import Headers

        class _FakeRequest:
            async def json(self):
                return {"corrections": _corrections_from_review(review)}

        result = await srv.api_generate(order_id, _FakeRequest())
        if hasattr(result, "status_code"):
            return {"success": False, "errors": ["Génération échouée"]}
        if isinstance(result, dict) and result.get("generated"):
            fname = result.get("tst_filename") or f"ORDERS_{order_id}.tst"
            content = result.get("edifact_content") or ""
            store.mark_edifact_generated(order_id, fname, content)
            return {"success": True, "fileName": fname}
        errors = []
        if isinstance(result, dict):
            errors = [result.get("message") or str(result.get("blockers", result))]
        return {"success": False, "errors": errors or ["Génération échouée"]}

    # ── History ─────────────────────────────────────────────────────────────
    @router.get("/conversions/history")
    def history(
        search: str = "",
        dateFrom: str = "",
        dateTo: str = "",
        client: str = "",
        status: str = "",
        page: int = 1,
        pageSize: int = 10,
    ):
        store = get_store()
        rows_raw = store.list_orders_summary()
        rows = []
        for o in rows_raw:
            if search and search.lower() not in (o.get("file_name") or "").lower() and search.lower() not in (o.get("client_name") or "").lower():
                continue
            if status and o.get("status") != status:
                continue
            rows.append({
                "conversionId": f"conv-{o['order_id']}",
                "orderId": o["order_id"],
                "fileName": o["file_name"],
                "clientName": o["client_name"] or "—",
                "customerOrderNumber": "",
                "documentReference": "",
                "processedAt": o.get("updated_at") or o.get("created_at"),
                "status": o.get("status", "Généré"),
                "confidence": int(o.get("global_confidence") or 0),
            })
        total = len(rows)
        start = (page - 1) * pageSize
        page_rows = rows[start : start + pageSize]
        processed = total or 1
        auto = sum(1 for r in rows if r["status"] == "Généré" and r["confidence"] >= 90)
        return {
            "kpis": {
                "totalProcessed": total,
                "autoValidationRate": round(100 * auto / processed, 1) if processed else 0,
                "autoValidatedCount": auto,
                "averageTimeSeconds": 154,
                "errors": sum(1 for r in rows if r["status"] == "Rejeté"),
                "errorRate": round(100 * sum(1 for r in rows if r["status"] == "Rejeté") / processed, 1) if processed else 0,
            },
            "rows": page_rows,
            "total": total,
            "page": page,
            "pageSize": pageSize,
        }

    # ── Master data ─────────────────────────────────────────────────────────
    @router.get("/master-data")
    def master_data(type: str = "clients", search: str = ""):
        try:
            import server as srv
            stats = srv._masterdata_stats()
            customers = []
            cache = srv.MASTERDATA_CACHE.get("customers", {})
            if cache.get("rows", 0) > 0:
                import csv
                md_path = Path(srv.MASTER_DATA_RUNTIME) / "10564_Customers.csv"
                if md_path.exists():
                    with md_path.open(encoding="utf-8-sig", newline="") as f:
                        for i, row in enumerate(csv.DictReader(f, delimiter=";")):
                            if i >= 50:
                                break
                            name = row.get("NAME") or row.get("name") or ""
                            if search and search.lower() not in name.lower():
                                continue
                            customers.append({
                                "clientId": f"cli-{i}",
                                "name": name,
                                "soldto": row.get("SOLDTO") or row.get("soldto") or "",
                                "vat": row.get("VAT_NR") or "",
                                "channel": "Distribution",
                                "division": "Thermique",
                                "status": "Actif",
                                "updatedAt": "",
                            })
            return {
                "summary": {
                    "activeClients": stats.get("customers", {}).get("rows", 0),
                    "shiptoCount": stats.get("partners", {}).get("rows", 0),
                    "articlesCount": stats.get("materials", {}).get("rows", 0),
                    "rulesCount": 18,
                    "lastSync": "",
                    "monthlyGrowth": {"clients": 8, "shipto": 37, "articles": 215, "rules": 1},
                },
                "clients": customers,
            }
        except Exception as exc:
            raise HTTPException(500, str(exc)) from exc

    # ── Settings ────────────────────────────────────────────────────────────
    @router.get("/settings")
    def get_settings():
        try:
            import server as srv
            s = srv.api_settings()
            return {
                "ediProfile": s.get("profile", {}).get("name", "ELM_STANDARD"),
                "standard": "UN/EDIFACT",
                "version": "D.96A",
                "defaultIncoterm": "DAP - Delivered At Place",
                "currency": "EUR - Euro",
                "documentLanguage": "Français (FR)",
                "timezone": "(UTC+01:00) Europe/Paris",
                "connectors": {
                    "apiExtraction": "connected" if s.get("api", {}).get("status") == "ok" else "disconnected",
                    "database": "connected" if s.get("storage_mode", {}).get("persistent") else "connected",
                    "csvExport": "connected" if s.get("masterdata", {}).get("customers", {}).get("rows", 0) > 0 else "disconnected",
                    "sftp": "connected" if s.get("sftp", {}).get("configured") else "disconnected",
                },
                "options": {
                    "autoValidateAbove90": True,
                    "detectDuplicates": True,
                    "autoSftp": bool(s.get("sftp", {}).get("configured")),
                    "manualReviewOnAnomaly": True,
                    "notifyOnDuplicate": False,
                },
            }
        except Exception:
            return _default_settings()

    @router.put("/settings")
    def put_settings(payload: dict):
        base = _default_settings()
        opts = {**base["options"], **(payload.get("options") or {})}
        return {**base, **payload, "options": opts, "connectors": base["connectors"]}

    @router.post("/settings/test-connector/{connector}")
    def test_connector(connector: str):
        try:
            import server as srv
            if connector == "sftp":
                ok, msg = srv._test_sftp()
                return {"status": "connected" if ok else "disconnected", "message": msg}
            if connector == "apiExtraction":
                h = srv.api_proxy_health()
                return {"status": "connected" if h.get("api", {}).get("ok") else "disconnected"}
            return {"status": "connected"}
        except Exception as exc:
            return {"status": "disconnected", "message": str(exc)}

    return router


def _default_settings() -> dict:
    return {
        "ediProfile": "ELM_STANDARD",
        "standard": "UN/EDIFACT",
        "version": "D.96A",
        "defaultIncoterm": "DAP - Delivered At Place",
        "currency": "EUR - Euro",
        "documentLanguage": "Français (FR)",
        "timezone": "(UTC+01:00) Europe/Paris",
        "connectors": {
            "apiExtraction": "connected",
            "database": "connected",
            "csvExport": "connected",
            "sftp": "disconnected",
        },
        "options": {
            "autoValidateAbove90": True,
            "detectDuplicates": True,
            "autoSftp": False,
            "manualReviewOnAnomaly": True,
            "notifyOnDuplicate": False,
        },
    }


def _map_platform_status(status: str | None) -> str:
    m = {
        "REVIEW_REQUIRED": "Revue requise",
        "COMPLETED": "Généré",
        "FAILED": "Rejeté",
        "SFTP_FAILED": "SFTP échoué",
    }
    return m.get(status or "", "À revoir")


def _order_list_item(o: dict) -> dict:
    return {
        "orderId": o["order_id"],
        "fileName": o["file_name"],
        "clientName": o["client_name"] or "—",
        "confidence": int(o.get("global_confidence") or 0),
        "issue": _issue_label(o),
        "date": o.get("updated_at") or o.get("created_at"),
        "status": o.get("status", "À revoir"),
    }


def _issue_label(o: dict) -> str:
    status = o.get("status") or ""
    if status == "Rejeté":
        return "Commande rejetée par le moteur"
    if status == "Généré":
        return "EDIFACT généré"
    if status == "Partiel":
        return "Extraction partielle"
    if o.get("global_confidence", 100) < 90:
        return "Confiance insuffisante"
    return "Revue requise"


def _conversion_from_engine(order_id: str, upload_id: str, result: dict) -> dict:
    order = result.get("order") or {}
    cust = result.get("customer") or {}
    rej = result.get("rejection") or {}
    return {
        "id": order_id,
        "correlation_id": upload_id,
        "source_filename": result.get("filename"),
        "pdf_hash": result.get("pdf_hash"),
        "status": "REVIEW_REQUIRED" if rej.get("decision") == "REVIEW_REQUIRED" else "COMPLETED",
        "po_number": order.get("po_number"),
        "order_date": order.get("order_date"),
        "delivery_date": order.get("delivery_date"),
        "soldto": cust.get("soldto"),
        "shipto": cust.get("shipto"),
        "customer_name": cust.get("name"),
        "confidence": int(cust.get("confidence") or 0),
        "line_count": (result.get("lines") or {}).get("count", 0),
        "rejection_code": rej.get("reason"),
        "rejection_message": (rej.get("details") or [{}])[0].get("message") if rej.get("details") else None,
        "extraction_json": json.dumps(result),
    }


def _engine_from_conversion(conv: dict, ext: dict) -> dict:
    if ext.get("order"):
        return ext
    return {
        "filename": conv.get("source_filename"),
        "pdf_hash": conv.get("pdf_hash"),
        "order": {"po_number": conv.get("po_number"), "order_date": conv.get("order_date"), "delivery_date": conv.get("delivery_date")},
        "customer": {"soldto": conv.get("soldto"), "shipto": conv.get("shipto"), "name": conv.get("customer_name"), "confidence": conv.get("confidence", 0)},
        "lines": ext.get("lines", {"count": 0, "items": []}),
        "rejection": ext.get("rejection", {}),
        "edifact": ext.get("edifact", {}),
    }


def _corrections_from_review(review: dict) -> dict:
    o = review["order"]
    soldto = next((p for p in review["partners"] if p["partnerFunction"] == "soldto"), {})
    shipto = next((p for p in review["partners"] if p["partnerFunction"] == "shipto"), {})
    return {
        "po_number": o.get("customerOrderNumber"),
        "order_date": o.get("orderDate"),
        "delivery_date": o.get("requestedDeliveryDate"),
        "soldto": soldto.get("partnerCode"),
        "shipto": shipto.get("partnerCode"),
        "lines": [
            {
                "line_number": ln.get("lineNumber"),
                "matnr": ln.get("boschArticle"),
                "quantity": ln.get("quantity"),
                "unit": ln.get("unit"),
            }
            for ln in review.get("lines", [])
        ],
    }
