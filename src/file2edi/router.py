"""FastAPI router — React File2EDI SPA contract (/api/*)."""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response

from .mapper import (
    dashboard_metrics_from_db,
    engine_to_extraction_preview,
    engine_to_order_review,
)
from .store import get_store
from .request_auth import ensure_admin, resolve_actor, resolve_role, resolve_role_for_request
from . import engine_bridge
from src.ai_status import build_system_health_payload
from src.health_probe import build_proxy_health
from src.masterdata_runtime import allowed_soldtos_for_actor, payload_for_scope, stats as masterdata_stats
from src.sftp_delivery import is_configured_from_env, test_connection_from_env


DEMO_ORDER_ID = "ord-rexel-026545008"


def _inject_resubmission_anomaly(store, order_id: str, review: dict) -> None:
    """Inject an informative anomaly if this PDF has already been submitted."""
    try:
        existing = store.load_order_review(order_id)
        if not existing:
            return
        prev_status = existing.get("order", {}).get("status") or "inconnu"
        prev_created = (existing.get("order", {}).get("createdAt") or "")[:10]
        prev_lines = len(existing.get("lines") or [])
        prev_total = existing.get("order", {}).get("totalAmount") or 0
        review["anomalies"].append({
            "anomalyId": f"resubmit-{order_id[:12]}",
            "orderId": order_id,
            "severity": "info",
            "fieldName": "RESUBMISSION_DETECTED",
            "message": (
                f"Ce PDF a déjà été soumis (première soumission: {prev_created or '—'}). "
                f"État précédent: {prev_status} — {prev_lines} ligne(s) — {prev_total:,.2f} €. "
                f"La commande est entièrement recalculée avec les patterns d'extraction actuels."
            ),
            "status": "Info",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass  # non-bloquant


# Cache du mapping SOLDTO → SAP ID gestionnaire (chargé depuis Partners CSV)
_SOLDTO_TO_ADV_SAPID: dict[str, str] = {}
_SOLDTO_CACHE_LOADED = False


def _load_soldto_adv_cache() -> None:
    """Charge le mapping SOLDTO → Fonction Partenaire (SAP ID ADV) depuis Partners CSV."""
    global _SOLDTO_TO_ADV_SAPID, _SOLDTO_CACHE_LOADED
    if _SOLDTO_CACHE_LOADED:
        return
    _SOLDTO_CACHE_LOADED = True  # évite double chargement même en cas d'erreur
    try:
        import os
        import pandas as pd
        # Cherche le fichier Partners dans les emplacements connus
        for path in (
            "/app/data/masterdata/10564_Partners.csv",
            os.path.join(os.path.dirname(__file__), "../..", "data/masterdata/10564_Partners.csv"),
        ):
            if os.path.exists(path):
                df = pd.read_csv(path, sep=";", dtype=str)
                col_fp = next((c for c in df.columns if "fonction" in c.lower() and "part" in c.lower()), None)
                col_soldto = next((c for c in df.columns if c.upper() == "SOLDTO"), None)
                if col_fp and col_soldto:
                    mapping = df.dropna(subset=[col_soldto, col_fp])
                    _SOLDTO_TO_ADV_SAPID = dict(
                        zip(mapping[col_soldto].astype(str).str.strip(),
                            mapping[col_fp].astype(str).str.strip())
                    )
                break
    except Exception as _e:
        import logging
        logging.getLogger("edifact.file2edi.router").debug("ADV cache load failed: %s", _e)


def _resolve_adv_username_from_soldto(soldto: str, store) -> str | None:
    """Retourne le username du gestionnaire ADV responsable d'un SOLDTO.
    
    Logique: SOLDTO → Partners CSV (Fonction Partenaire = SAP ID ADV)
             → file2edi_users.sap_id → username
    """
    _load_soldto_adv_cache()
    adv_sap_id = _SOLDTO_TO_ADV_SAPID.get(str(soldto).strip())
    if not adv_sap_id:
        return None
    try:
        users = store.list_users()
        for user in users:
            if str(user.get("sapId") or "").strip() == str(adv_sap_id).strip():
                return user["username"]
    except Exception:
        pass
    return None


def _parse_custom_headers(raw: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for part in re.split(r"[\n,]", raw or ""):
        chunk = part.strip()
        if not chunk or ":" not in chunk:
            continue
        key, value = chunk.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            headers[key] = value
    return headers


def _apply_runtime_sftp_config(settings_payload: dict | None) -> None:
    """Apply SFTP settings to runtime env used by legacy send/test helpers."""
    if not isinstance(settings_payload, dict):
        return
    sftp = settings_payload.get("sftpConfig")
    if not isinstance(sftp, dict):
        return

    host = str(sftp.get("host") or "").strip()
    username = str(sftp.get("username") or "").strip()
    remote = str(sftp.get("remotePath") or "").strip()

    if host:
        os.environ["SFTP_HOST"] = host
    else:
        os.environ.pop("SFTP_HOST", None)

    if username:
        os.environ["SFTP_USERNAME"] = username
    else:
        os.environ.pop("SFTP_USERNAME", None)

    if remote:
        os.environ["SFTP_REMOTE_DIR"] = remote
    else:
        os.environ.pop("SFTP_REMOTE_DIR", None)

    try:
        port = int(sftp.get("port") or 22)
    except (TypeError, ValueError):
        port = 22
    os.environ["SFTP_PORT"] = str(max(1, min(65535, port)))


def create_router() -> APIRouter:
    router = APIRouter(tags=["file2edi"])

    # ── Auth: session cookie helpers ────────────────────────────────────────
    SESSION_COOKIE = "f2edi_session"

    def _get_current_user(req: Request) -> dict | None:
        """Extract authenticated user from session cookie."""
        session_id = req.cookies.get(SESSION_COOKIE)
        if not session_id:
            return None
        try:
            return get_store().get_session_user(session_id)
        except Exception:
            return None

    @router.get("/auth/modes")
    def auth_modes():
        return {"profile_login_enabled": True, "workspace_sso_available": False, "allowed_roles": ["user"]}

    @router.post("/auth/login")
    async def auth_login(req: Request):
        from fastapi.responses import JSONResponse
        body = await req.json()
        username = str(body.get("actor") or body.get("username") or "").strip()
        password = str(body.get("password") or "").strip()
        if not username or not password:
            raise HTTPException(400, "Identifiant et mot de passe requis")
        user = get_store().verify_credentials(username, password)
        if not user:
            raise HTTPException(401, "Identifiant ou mot de passe incorrect")
        session_id = get_store().create_session(user["userId"], ip=req.client.host if req.client else None)
        resp = JSONResponse({"ok": True, "actor": user["username"], "displayName": user["displayName"], "role": "admin"})
        resp.set_cookie(SESSION_COOKIE, session_id, httponly=True, samesite="lax", max_age=43200)
        return resp

    @router.post("/auth/logout")
    async def auth_logout(req: Request):
        from fastapi.responses import JSONResponse
        session_id = req.cookies.get(SESSION_COOKIE)
        if session_id:
            try:
                get_store().invalidate_session(session_id)
            except Exception:
                pass
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(SESSION_COOKIE)
        return resp

    @router.get("/me")
    def get_me(req: Request):
        """Return current user info — prefers session cookie, falls back to server actor.
        
        If a f2edi_session cookie is present but invalid/expired, return authenticated=False
        so the frontend shows the login page (prevents bypassing logout via DEV_ACTOR fallback).
        """
        session_id = req.cookies.get(SESSION_COOKIE)

        # Cookie present → must validate it; don't fall back to DEV_ACTOR
        if session_id:
            user = _get_current_user(req)
            if user:
                return {"actor": user["username"], "username": user["username"],
                        "displayName": user["displayName"],
                        "role": user.get("role", "adv"), "authenticated": True}
            # Cookie present but invalid/expired → force re-login
            return {"actor": None, "authenticated": False, "role": "adv"}

        # No cookie → try session-based auth from session store (might have users)
        try:
            users = get_store().list_users()
            if users:
                # Users exist in DB → require login
                return {"actor": None, "authenticated": False, "role": "adv"}
        except Exception:
            pass

        # No users in DB → dev/demo mode: fall back to server actor
        try:
            actor = resolve_actor(req)
            role = resolve_role(actor)
            return {"actor": actor, "displayName": actor, "role": role or "admin", "authenticated": True}
        except Exception:
            return {"actor": "operator", "displayName": "Opérateur", "role": "admin", "authenticated": True}

    # ── User management ───────────────────────────────────────────────────────
    @router.get("/users")
    def list_users():
        try:
            return get_store().list_users()
        except Exception:
            return []

    @router.post("/users")
    async def create_user(req: Request):
        body = await req.json()
        username = str(body.get("username") or "").strip().lower()
        display_name = str(body.get("displayName") or body.get("display_name") or username).strip()
        password = str(body.get("password") or "").strip()
        email = str(body.get("email") or "").strip()
        sap_id = str(body.get("sapId") or body.get("sap_id") or "").strip()
        role = str(body.get("role") or "adv").strip().lower()
        if role not in ("adv", "admin"):
            role = "adv"
        if not username or not password:
            raise HTTPException(400, "Identifiant et mot de passe requis")
        try:
            return get_store().create_user(username, display_name, password,
                                           email=email, sap_id=sap_id, role=role)
        except Exception as exc:
            raise HTTPException(400, f"Impossible de créer l'utilisateur: {exc}")

    @router.delete("/users/{user_id}")
    def delete_user(user_id: str):
        get_store().delete_user(user_id)
        return {"ok": True}

    @router.put("/users/{user_id}")
    async def update_user(user_id: str, req: Request):
        body = await req.json()
        display_name = body.get("displayName") or body.get("display_name")
        email = body.get("email")
        sap_id = body.get("sapId") or body.get("sap_id")
        role = body.get("role")
        result = get_store().update_user(
            user_id,
            display_name=display_name,
            email=email,
            sap_id=sap_id,
            role=role,
        )
        if not result:
            raise HTTPException(404, "Utilisateur introuvable")
        return result

    @router.post("/users/{user_id}/change-password")
    async def user_change_password(user_id: str, req: Request):
        body = await req.json()
        password = str(body.get("password") or "").strip()
        if not password:
            raise HTTPException(400, "Mot de passe requis")
        get_store().change_password(user_id, password)
        return {"ok": True}

    # ── Order workflow actions ─────────────────────────────────────────────────
    @router.post("/orders/{order_id}/hold")
    async def hold_order(order_id: str, req: Request):
        _require_mutable_order(order_id)
        body = await req.json()
        reason = str(body.get("reason") or "").strip()
        if not reason:
            raise HTTPException(400, "Motif de mise en attente requis")
        user = _get_current_user(req)
        actor = user["username"] if user else "operator"
        result = get_store().hold_order(order_id, reason, actor)
        if not result:
            raise HTTPException(404)
        return {"ok": True, "status": "En attente", "reason": reason}

    @router.post("/orders/{order_id}/reject")
    async def reject_order(order_id: str, req: Request):
        _require_mutable_order(order_id)
        body = await req.json()
        reason = str(body.get("reason") or "").strip()
        if not reason:
            raise HTTPException(400, "Motif de rejet requis")
        user = _get_current_user(req)
        actor = user["username"] if user else "operator"
        result = get_store().reject_order(order_id, reason, actor)
        if not result:
            raise HTTPException(404)
        return {"ok": True, "status": "Rejeté", "reason": reason}

    @router.post("/orders/{order_id}/transfer")
    async def transfer_order(order_id: str, req: Request):
        _require_mutable_order(order_id)
        body = await req.json()
        to_username = str(body.get("to") or "").strip()
        note = str(body.get("note") or "").strip()
        if not to_username:
            raise HTTPException(400, "Destinataire requis")
        user = _get_current_user(req)
        from_actor = user["username"] if user else "operator"
        result = get_store().transfer_order(order_id, to_username, note, from_actor)
        if not result:
            raise HTTPException(404)
        return {"ok": True, "status": "Transféré", "to": to_username}

    # ── Health (React Header badges) ─────────────────────────────────────────
    @router.get("/health/system")
    def health_system():
        try:
            return build_system_health_payload(build_proxy_health())
        except Exception:
            return {
                "api": "disconnected",
                "database": "disconnected",
                "csv": "disconnected",
                "sftp": "disconnected",
                "ai": "disconnected",
            }

    # ── Dashboard ───────────────────────────────────────────────────────────
    @router.get("/dashboard/metrics")
    def dashboard_metrics(req: Request):
        actor = resolve_actor(req)
        role = resolve_role(actor)
        orders = _list_combined_orders(actor=actor, role=role, include_done=True)
        return dashboard_metrics_from_db(orders)

    @router.get("/orders")
    def list_orders(req: Request):
        """All converted orders for the Revue list page."""
        actor = resolve_actor(req)
        role = resolve_role(actor)
        return [_order_list_item(o) for o in _list_combined_orders(actor=actor, role=role, include_done=True)]

    @router.get("/dashboard/review-queue")
    def review_queue(req: Request):
        actor = resolve_actor(req)
        role = resolve_role(actor)
        items: list[dict] = []
        try:
            review_statuses = ("Revue requise", "À revoir", "À vérifier", "Bloqué")
            items = [
                _order_list_item(o)
                for o in _list_combined_orders(actor=actor, role=role, include_done=True)
                if o.get("status") in review_statuses
            ]
        except Exception:
            items = []

        if not items:
            try:
                for c in engine_bridge.list_conversions(status="REVIEW_REQUIRED", limit=20):
                    try:
                        conf = int(float(c.get("confidence") or 0))
                    except Exception:
                        conf = 0
                    items.append({
                        "orderId": c.get("id"),
                        "fileName": c.get("source_filename"),
                        "clientName": c.get("customer_name") or "—",
                        "confidence": conf,
                        "issue": c.get("rejection_message") or c.get("rejection_code") or "Revue requise",
                        "date": c.get("created_at"),
                        "status": "À revoir",
                    })
            except Exception:
                return []
        return items[:20]

    @router.get("/dashboard/recent-conversions")
    def recent_conversions(req: Request):
        actor = resolve_actor(req)
        role = resolve_role(actor)
        out = []
        for o in _list_combined_orders(actor=actor, role=role, include_done=True)[:10]:
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
    async def upload_pdf(req: Request, pdf: UploadFile = File(...)):
        if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "PDF requis")
        payload = await pdf.read()
        if len(payload) > 20 * 1024 * 1024:
            raise HTTPException(400, "Fichier trop volumineux (max 20 Mo)")
        store = get_store()
        upload_id = f"upl-{uuid.uuid4().hex[:12]}"
        dest = store.intake_dir / f"{upload_id}.pdf"
        dest.write_bytes(payload)
        uploaded_by = resolve_actor(req)
        meta = store.save_upload_with_id(upload_id, pdf.filename, len(payload), str(dest), uploaded_by=uploaded_by)
        return {"uploadId": meta["uploadId"]}

    @router.post("/upload/{upload_id}/extract")
    def extract_upload(upload_id: str):
        store = get_store()
        pdf_path = store.get_upload_path(upload_id)
        if not pdf_path:
            raise HTTPException(404, "Upload introuvable")
        upload_meta = store.get_upload_meta(upload_id) or {}
        uploaded_by = str(upload_meta.get("uploaded_by") or "operator")
        payload = pdf_path.read_bytes()
        result = engine_bridge.process_pdf(payload, pdf_path.name, actor=uploaded_by)
        assigned_actor = engine_bridge.resolve_processing_actor(uploaded_by, result)
        order_id = result.get("pdf_hash") or f"ord-{uuid.uuid4().hex[:12]}"
        page_count = 3
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                page_count = len(pdf.pages)
        except Exception:
            pass
        review = engine_to_order_review(order_id, upload_id, result)
        if upload_meta.get("file_name"):
            review["order"]["fileName"] = upload_meta["file_name"]
        review["order"]["pdfPath"] = str(pdf_path)
        review["order"]["processedBy"] = assigned_actor
        review["order"]["source"] = "ui"
        # Détecter re-soumission
        _inject_resubmission_anomaly(store, order_id, review)
        # Auto-assigner au gestionnaire ADV selon Fonction Partenaire dans Partners
        soldto = next((p.get("partnerCode") for p in review.get("partners", [])
                       if p.get("partnerFunction") == "soldto"), None)
        if soldto:
            adv_username = _resolve_adv_username_from_soldto(soldto, store)
            if adv_username:
                review["order"]["assignedTo"] = adv_username
        store.save_order_review(review)
        try:
            engine_bridge.init_db()
            engine_bridge.upsert_conversion(_conversion_from_engine(order_id, upload_id, result, operator=assigned_actor))
        except Exception:
            pass
        return engine_to_extraction_preview(
            upload_id, order_id, result, len(payload), page_count=page_count,
        )

    @router.post("/extract")
    @router.post("/upload/extract")
    async def extract_pdf_direct(req: Request, pdf: UploadFile = File(...)):
        """One-shot local extraction API: upload + extract in a single call."""
        if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "PDF requis")
        payload = await pdf.read()
        if len(payload) > 20 * 1024 * 1024:
            raise HTTPException(400, "Fichier trop volumineux (max 20 Mo)")

        store = get_store()
        upload_id = f"upl-{uuid.uuid4().hex[:12]}"
        dest = store.intake_dir / f"{upload_id}.pdf"
        dest.write_bytes(payload)

        uploaded_by = resolve_actor(req)
        meta = store.save_upload_with_id(upload_id, pdf.filename, len(payload), str(dest), uploaded_by=uploaded_by)

        result = engine_bridge.process_pdf(payload, pdf.filename, actor=uploaded_by)
        assigned_actor = engine_bridge.resolve_processing_actor(uploaded_by, result)
        order_id = result.get("pdf_hash") or f"ord-{uuid.uuid4().hex[:12]}"

        page_count = 3
        try:
            import pdfplumber

            with pdfplumber.open(dest) as opened:
                page_count = len(opened.pages)
        except Exception:
            pass

        review = engine_to_order_review(order_id, upload_id, result)
        review["order"]["fileName"] = meta.get("file_name") or pdf.filename
        review["order"]["pdfPath"] = str(dest)
        review["order"]["processedBy"] = assigned_actor
        review["order"]["source"] = "api"
        # Détecter re-soumission
        _inject_resubmission_anomaly(store, order_id, review)
        # Auto-assigner au gestionnaire ADV selon Fonction Partenaire dans Partners
        soldto = next((p.get("partnerCode") for p in review.get("partners", [])
                       if p.get("partnerFunction") == "soldto"), None)
        if soldto:
            adv_username = _resolve_adv_username_from_soldto(soldto, store)
            if adv_username:
                review["order"]["assignedTo"] = adv_username
        store.save_order_review(review)

        try:
            engine_bridge.init_db()
            engine_bridge.upsert_conversion(_conversion_from_engine(order_id, upload_id, result, operator=assigned_actor))
        except Exception:
            pass

        preview = engine_to_extraction_preview(
            upload_id,
            order_id,
            result,
            len(payload),
            page_count=page_count,
        )
        return {
            "uploadId": upload_id,
            "orderId": order_id,
            "preview": preview,
            "result": result,
        }

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
                conv = engine_bridge.load_conversion(order_id)
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
        return _with_sap_resend_cooldown(review)

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
    async def patch_order(order_id: str, payload: dict = Body(...)):
        try:
            review = get_store().update_order_header(order_id, payload)
        except Exception as exc:
            raise HTTPException(500, f"Mise à jour commande échouée: {exc}") from exc
        if not review:
            raise HTTPException(404)
        return review

    @router.patch("/orders/partners/{partner_id}")
    async def patch_partner(partner_id: str, payload: dict = Body(...)):
        try:
            review = get_store().update_partner(partner_id, payload)
        except Exception as exc:
            raise HTTPException(500, f"Mise à jour partenaire échouée: {exc}") from exc
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

    @router.delete("/uploads/{upload_id}")
    async def delete_upload(upload_id: str):
        deleted = get_store().delete_upload(upload_id)
        if not deleted:
            raise HTTPException(404)
        return {"deleted": upload_id}

    @router.patch("/orders/anomalies/{anomaly_id}")
    async def patch_anomaly(anomaly_id: str, payload: dict):
        action = payload.get("action", "corrected")
        review = get_store().resolve_anomaly(anomaly_id, action)
        if not review:
            raise HTTPException(404)
        return review

    @router.post("/orders/{order_id}/save")
    async def save_order(order_id: str, req: Request):
        store = get_store()
        try:
            actor = resolve_actor(req)
        except Exception:
            actor = "operator"
        review = store.save_order_snapshot(order_id, actor=actor)
        if not review:
            raise HTTPException(404)
        blockers = _mandatory_review_errors(review)
        return {
            "success": True,
            "message": "Modifications enregistrées",
            "blockers": blockers,
            "review": review,
        }

    @router.post("/orders/{order_id}/generate-edifact")
    async def generate_edifact(order_id: str, req: Request):
        store = get_store()
        review = store.load_order_review(order_id)
        if not review:
            raise HTTPException(404)

        mandatory_errors = _mandatory_review_errors(review)
        if mandatory_errors:
            return {"success": False, "errors": mandatory_errors}

        _ensure_conversion_for_generate(order_id, review)

        class _FakeRequest:
            headers: dict[str, str] = {}
            cookies: dict[str, str] = {}

            async def json(self):
                return {"corrections": _corrections_from_review(review)}

        result = await engine_bridge.generate_edifact(order_id, _FakeRequest())
        if hasattr(result, "status_code"):
            body = getattr(result, "body", b"") or b""
            try:
                detail = json.loads(body).get("error", "Conversion introuvable")
            except Exception:
                detail = "Conversion introuvable"
            return {"success": False, "errors": [detail]}
        if isinstance(result, dict) and result.get("generated"):
            fname = result.get("tst_filename") or f"ORDERS_{order_id}.tst"
            content = result.get("edifact_content") or ""
            try:
                _actor = resolve_actor(req)
            except Exception:
                _actor = "operator"
            store.mark_edifact_generated(order_id, fname, content, actor=_actor)
            return {"success": True, "fileName": fname, "content": content}
        if isinstance(result, dict):
            return {"success": False, "errors": _extract_generate_errors(result)}
        return {"success": False, "errors": ["Génération échouée"]}

    @router.post("/orders/{order_id}/send-sftp")
    @router.post("/orders/{order_id}/send-sap")
    async def send_to_sap(
        order_id: str,
        req: Request,
        payload: dict = Body(default_factory=dict),
    ):
        import tempfile
        from src.sftp_delivery import upload_tst

        store = get_store()
        export = store.get_edifact_export(order_id)
        if not export:
            raise HTTPException(400, "EDIFACT non généré pour cette commande")

        # Align runtime SFTP env with persisted app settings before sending.
        _apply_runtime_sftp_config(store.load_app_settings())
        sent_by = resolve_actor(req)
        actor_role = resolve_role_for_request(sent_by, req)

        try:
            force_resend = bool((payload or {}).get("force"))
            ignore_cooldown = bool((payload or {}).get("ignoreCooldown"))
            already_sent = False
            cooldown = {
                "active": False,
                "remainingSeconds": 0,
                "cooldownSeconds": _sap_resend_cooldown_seconds(),
                "resendAvailableAt": None,
            }
            try:
                review = store.load_order_review(order_id) or {}
                order_meta = review.get("order") or {}
                already_sent = _order_sent_to_sap(order_meta)
                if already_sent:
                    cooldown = _sap_resend_cooldown_info(order_meta)
            except Exception:
                already_sent = False
            if already_sent:
                if actor_role != "admin":
                    return {
                        "success": False,
                        "alreadySent": True,
                        "cooldownActive": cooldown["active"],
                        "remainingSeconds": cooldown["remainingSeconds"],
                        "cooldownSeconds": cooldown["cooldownSeconds"],
                        "resendAvailableAt": cooldown["resendAvailableAt"],
                        "message": "Cette commande a déjà été envoyée vers SAP.",
                    }
                if cooldown["active"] and not ignore_cooldown:
                    return {
                        "success": False,
                        "alreadySent": True,
                        "requiresConfirmation": True,
                        "cooldownActive": True,
                        "remainingSeconds": cooldown["remainingSeconds"],
                        "cooldownSeconds": cooldown["cooldownSeconds"],
                        "resendAvailableAt": cooldown["resendAvailableAt"],
                        "message": (
                            f"Renvoi possible dans {_format_cooldown_mmss(int(cooldown['remainingSeconds']))}. "
                            "Un administrateur peut ignorer ce délai."
                        ),
                    }
                if not force_resend:
                    return {
                        "success": False,
                        "alreadySent": True,
                        "requiresConfirmation": True,
                        "cooldownActive": False,
                        "remainingSeconds": 0,
                        "cooldownSeconds": cooldown["cooldownSeconds"],
                        "resendAvailableAt": cooldown["resendAvailableAt"],
                        "message": "Cette commande a déjà été envoyée vers SAP. Confirmez pour renvoyer.",
                    }

            host = (os.environ.get("SFTP_HOST") or "").strip()
            username = (os.environ.get("SFTP_USERNAME") or "").strip()
            remote_dir = (os.environ.get("SFTP_REMOTE_DIR") or "").strip()
            password = os.environ.get("SFTP_PASSWORD") or ""
            private_key_path = os.environ.get("SFTP_PRIVATE_KEY_PATH") or ""
            if not host or not username or not remote_dir or not (password or private_key_path):
                missing = []
                if not host:
                    missing.append("SFTP_HOST")
                if not username:
                    missing.append("SFTP_USERNAME")
                if not remote_dir:
                    missing.append("SFTP_REMOTE_DIR")
                if not (password or private_key_path):
                    missing.append("SFTP_PASSWORD or SFTP_PRIVATE_KEY_PATH")
                detail = f"Configuration SFTP incomplète: {', '.join(missing)}"
                store.mark_sftp_delivery(order_id, False, detail)
                return {"success": False, "message": detail}

            try:
                port = int(os.environ.get("SFTP_PORT") or "22")
            except Exception:
                port = 22
            try:
                max_retries = int(os.environ.get("SFTP_MAX_RETRIES") or "3")
            except Exception:
                max_retries = 3

            cfg = type("RuntimeSftpConfig", (), {
                "enabled": True,
                "host": host,
                "port": max(1, min(65535, port)),
                "username": username,
                "password": password,
                "private_key_path": private_key_path,
                "private_key_passphrase": os.environ.get("SFTP_PRIVATE_KEY_PASSPHRASE") or "",
                "remote_dir": remote_dir,
                "upload_tmp_suffix": os.environ.get("SFTP_UPLOAD_TMP_SUFFIX") or ".uploading",
                "verify_after_upload": (os.environ.get("SFTP_VERIFY_AFTER_UPLOAD") or "true").strip().lower()
                not in {"0", "false", "no", "off"},
                "max_retries": max(1, max_retries),
                "keep_local_copy": True,
            })()

            filename = Path(str(export.get("fileName") or f"ORDERS_{order_id}.tst")).name
            with tempfile.TemporaryDirectory(prefix="file2edi-sftp-") as tmp_dir:
                local_path = Path(tmp_dir) / filename
                local_path.write_text(str(export.get("content") or ""), encoding="utf-8", newline="")
                result = upload_tst(local_path, filename, cfg)

            if result.success:
                store.mark_sftp_delivery(order_id, True, result.remote_path, sent_by=sent_by)
                remote = str(result.remote_path or "")
                return {
                    "success": True,
                    "ok": True,
                    "alreadySent": already_sent,
                    "message": f"Fichier envoyé vers SAP (SFTP) {remote}".strip(),
                    "remote_path": remote,
                    "sapSentBy": sent_by,
                }

            store.mark_sftp_delivery(order_id, False, result.error_reason)
            return {"success": False, "message": str(result.error_reason or "Échec envoi SFTP")}
        except Exception as exc:
            try:
                store.mark_sftp_delivery(order_id, False, str(exc))
            except Exception:
                pass
            return {"success": False, "message": f"Échec envoi SFTP: {exc}"}

    @router.get("/orders/{order_id}/edifact")
    def download_edifact(order_id: str):
        export = get_store().get_edifact_export(order_id)
        if not export:
            raise HTTPException(404, "Aucun fichier EDIFACT généré pour cette commande")
        fname = export["fileName"]
        return Response(
            content=export["content"],
            media_type="application/edifact",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )

    # ── History ─────────────────────────────────────────────────────────────
    @router.get("/conversions/history")
    def history(
        req: Request,
        search: str = "",
        dateFrom: str = "",
        dateTo: str = "",
        client: str = "",
        status: str = "",
        page: int = 1,
        pageSize: int = 10,
    ):
        import server as srv
        actor = srv._resolve_actor(req)
        role = srv._resolve_role(actor)
        rows_raw = _list_combined_orders(actor=actor, role=role, include_done=True)
        rows = []
        for o in rows_raw:
            if search and search.lower() not in (o.get("file_name") or "").lower() and search.lower() not in (o.get("client_name") or "").lower():
                continue
            if status:
                allowed = {s.strip() for s in status.split(",") if s.strip()}
                if allowed and o.get("status") not in allowed:
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
    def master_data(
        req: Request,
        type: str = "clients",
        search: str = "",
        limit: int = 100,
    ):
        try:
            actor = resolve_actor(req)
            role = resolve_role(actor)
            allowed = allowed_soldtos_for_actor(actor, role)
            return payload_for_scope(allowed, type, search, limit)
        except Exception as exc:
            raise HTTPException(500, str(exc)) from exc

    # ── Settings ────────────────────────────────────────────────────────────
    @router.get("/settings")
    def get_settings():
        try:
            h = build_proxy_health()
            persisted = get_store().load_app_settings()
            md = masterdata_stats() or {}
            csv_rows = int((md.get("customers") or {}).get("rows", 0) or 0)
            return {
                "ediProfile": "ELM_STANDARD",
                "standard": "UN/EDIFACT",
                "version": "D.96A",
                "defaultIncoterm": persisted.get("defaultIncoterm", "DAP - Delivered At Place"),
                "currency": persisted.get("currency", "EUR - Euro"),
                "documentLanguage": persisted.get("documentLanguage", "Français (FR)"),
                "timezone": persisted.get("timezone", "(UTC+01:00) Europe/Paris"),
                "connectors": {
                    "apiExtraction": "connected" if h.get("api", {}).get("ok") else "disconnected",
                    "database": "connected" if h.get("database", {}).get("ok") else "disconnected",
                    "csvExport": "connected" if h.get("masterdata", {}).get("ok") and csv_rows > 0 else "disconnected",
                    "sftp": "connected" if is_configured_from_env() else "disconnected",
                },
                "connectorConfig": persisted.get("connectorConfig", _default_settings().get("connectorConfig", {})),
                "masterdataN8nConfig": {
                    **_default_settings().get("masterdataN8nConfig", {}),
                    **(persisted.get("masterdataN8nConfig") or {}),
                },
                "aiProvider": persisted.get("aiProvider", _default_settings().get("aiProvider", "databricks")),
                "databricksConfig": {
                    **_default_settings().get("databricksConfig", {}),
                    **(persisted.get("databricksConfig") or {}),
                },
                "openaiConfig": {
                    **_default_settings().get("openaiConfig", {}),
                    **(persisted.get("openaiConfig") or {}),
                },
                "ollamaConfig": {
                    **_default_settings().get("ollamaConfig", {}),
                    **(persisted.get("ollamaConfig") or {}),
                },
                "customAiConfig": {
                    **_default_settings().get("customAiConfig", {}),
                    **(persisted.get("customAiConfig") or {}),
                },
                "validation": persisted.get("validation", _default_settings().get("validation", {})),
                "notifications": persisted.get("notifications", _default_settings().get("notifications", {})),
                "sftpConfig": {
                    **_default_settings().get("sftpConfig", {}),
                    **(persisted.get("sftpConfig") or {}),
                    "hasPassword": bool(os.environ.get("SFTP_PASSWORD", "")),
                },
                "security": persisted.get("security", _default_settings().get("security", {})),
                "options": persisted.get("options", _default_settings().get("options", {})),
            }
        except Exception:
            return _default_settings()

    @router.put("/settings")
    def put_settings(payload: dict, req: Request):
        try:
            ensure_admin(req)
        except HTTPException:
            raise
        except Exception:
            pass

        persisted = get_store().save_app_settings(payload or {})
        try:
            from src.ai_status import apply_runtime_ai_config

            apply_runtime_ai_config(persisted)
        except Exception:
            pass
        _apply_runtime_sftp_config(persisted)
        settings = _default_settings()
        settings.update({
            "defaultIncoterm": persisted.get("defaultIncoterm", settings["defaultIncoterm"]),
            "currency": persisted.get("currency", settings["currency"]),
            "documentLanguage": persisted.get("documentLanguage", settings["documentLanguage"]),
            "timezone": persisted.get("timezone", settings["timezone"]),
            "aiProvider": persisted.get("aiProvider", settings.get("aiProvider", "databricks")),
        })
        settings["connectorConfig"] = {**settings.get("connectorConfig", {}), **(persisted.get("connectorConfig") or {})}
        settings["masterdataN8nConfig"] = {
            **settings.get("masterdataN8nConfig", {}),
            **(persisted.get("masterdataN8nConfig") or {}),
        }
        settings["databricksConfig"] = {**settings.get("databricksConfig", {}), **(persisted.get("databricksConfig") or {})}
        settings["openaiConfig"] = {**settings.get("openaiConfig", {}), **(persisted.get("openaiConfig") or {})}
        settings["ollamaConfig"] = {**settings.get("ollamaConfig", {}), **(persisted.get("ollamaConfig") or {})}
        settings["customAiConfig"] = {**settings.get("customAiConfig", {}), **(persisted.get("customAiConfig") or {})}
        settings["validation"] = {**settings.get("validation", {}), **(persisted.get("validation") or {})}
        settings["notifications"] = {**settings.get("notifications", {}), **(persisted.get("notifications") or {})}
        settings["sftpConfig"] = {**settings.get("sftpConfig", {}), **(persisted.get("sftpConfig") or {})}
        settings["sftpConfig"]["hasPassword"] = bool(os.environ.get("SFTP_PASSWORD", ""))
        settings["security"] = {**settings.get("security", {}), **(persisted.get("security") or {})}
        settings["options"] = {**settings["options"], **(persisted.get("options") or {})}
        return settings

    @router.post("/settings/test-connector/{connector}")
    def test_connector(connector: str, payload: dict = Body(default_factory=dict)):
        try:
            if connector == "sftp":
                persisted = get_store().load_app_settings()
                merged_sftp = dict((persisted or {}).get("sftpConfig") or {})
                incoming_sftp = (payload or {}).get("sftpConfig")
                if isinstance(incoming_sftp, dict):
                    merged_sftp.update(incoming_sftp)
                _apply_runtime_sftp_config({"sftpConfig": merged_sftp})
                ok, msg = test_connection_from_env()
                return {"status": "connected" if ok else "disconnected", "message": msg}
            if connector == "apiExtraction":
                configured_base = str(((payload or {}).get("connectorConfig") or {}).get("apiBaseUrl") or "").strip().rstrip("/")
                if configured_base:
                    import requests as _requests

                    candidate_paths = ["", "/health", "/api/health", "/api/proxy/health"]
                    for path in candidate_paths:
                        url = f"{configured_base}{path}"
                        try:
                            resp = _requests.get(url, timeout=5)
                            if resp.status_code < 500:
                                return {
                                    "status": "connected",
                                    "message": f"API extraction joignable: {url}",
                                }
                        except Exception:
                            continue
                    return {
                        "status": "disconnected",
                        "message": f"API extraction indisponible sur {configured_base}",
                    }

                h = build_proxy_health()
                ok = bool(h.get("api", {}).get("ok"))
                return {
                    "status": "connected" if ok else "disconnected",
                    "message": "API extraction locale opérationnelle" if ok else "API extraction indisponible",
                }
            if connector == "database":
                h = build_proxy_health()
                db = h.get("database", {}) if isinstance(h, dict) else {}
                ok = bool(db.get("ok"))
                backend = str(db.get("backend") or "unknown")
                return {
                    "status": "connected" if ok else "disconnected",
                    "message": f"Backend: {backend}",
                }
            if connector == "csvExport":
                incoming_n8n = (payload or {}).get("masterdataN8nConfig")
                if isinstance(incoming_n8n, dict) and (
                    incoming_n8n.get("enabled") or incoming_n8n.get("webhookUrl")
                ):
                    import requests as _requests

                    persisted = get_store().load_app_settings()
                    merged = {
                        **((persisted or {}).get("masterdataN8nConfig") or {}),
                        **incoming_n8n,
                    }
                    url = str(merged.get("webhookUrl") or "").strip()
                    if not url:
                        return {"status": "disconnected", "message": "URL webhook n8n manquante"}
                    try:
                        # Prefer OPTIONS/HEAD-less: POST with dryRun flag; many n8n webhooks accept POST only.
                        resp = _requests.post(
                            url,
                            json={"action": "masterdata_sync", "reason": "connectivity_test", "dryRun": True},
                            timeout=10,
                        )
                        if resp.status_code < 500:
                            return {
                                "status": "connected",
                                "message": f"Webhook n8n joignable (HTTP {resp.status_code})",
                            }
                        return {
                            "status": "disconnected",
                            "message": f"Webhook n8n HTTP {resp.status_code}",
                        }
                    except Exception as exc:
                        return {"status": "disconnected", "message": f"Webhook n8n injoignable: {exc}"}
                stats = masterdata_stats()
                if not isinstance(stats, dict) or not stats:
                    return {"status": "disconnected", "message": "Aucune source CSV chargée"}
                missing_rows = [name for name, st in stats.items() if int((st or {}).get("rows") or 0) <= 0]
                invalid_schema = [name for name, st in stats.items() if (st or {}).get("schema_valid") is False]
                if missing_rows:
                    return {
                        "status": "disconnected",
                        "message": f"CSV sans données: {', '.join(missing_rows)}",
                    }
                if invalid_schema:
                    return {
                        "status": "disconnected",
                        "message": f"Schéma CSV invalide: {', '.join(invalid_schema)}",
                    }
                return {"status": "connected", "message": "Sources CSV chargées et valides"}
            return {"status": "disconnected", "message": f"Connecteur non supporté: {connector}"}
        except Exception as exc:
            return {"status": "disconnected", "message": str(exc)}

    @router.post("/settings/ai-test")
    def test_ai_connection(payload: dict = Body(default_factory=dict)):
        """Test the configured AI provider connection with current or provided config."""
        import os as _os
        import requests as _requests
        provider = str((payload or {}).get("provider") or _os.environ.get("F2EDI_LLM_PROVIDER", "databricks")).strip().lower()
        target = str((payload or {}).get("host") or (payload or {}).get("baseUrl") or "").strip().rstrip("/")

        try:
            if provider == "databricks":
                if isinstance(payload, dict) and "host" in payload:
                    host = str(payload.get("host") or "").strip().rstrip("/")
                else:
                    host = str(_os.environ.get("DATABRICKS_HOST", "")).strip().rstrip("/")
                target = host
                token = str((payload or {}).get("token") or _os.environ.get("DATABRICKS_TOKEN", "")).strip()
                endpoint = str(
                    (payload or {}).get("modelEndpoint")
                    or _os.environ.get("DATABRICKS_MODEL_ENDPOINT", "databricks-gpt-oss-120b")
                ).strip()
                if not host:
                    return {"ok": False, "message": "DATABRICKS_HOST non configuré"}
                url = f"{host}/serving-endpoints/{endpoint}/invocations"
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                else:
                    try:
                        from databricks.sdk import WorkspaceClient
                        profile = _os.environ.get("DATABRICKS_CONFIG_PROFILE", "").strip()
                        w = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
                        auth_h = w.config.authenticate()
                        headers.update(auth_h)
                    except Exception as exc:
                        return {"ok": False, "message": f"Authentification impossible: {exc}"}
                body = {
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                }
                resp = _requests.post(url, headers=headers, json=body, timeout=15)
                if resp.status_code == 200:
                    return {"ok": True, "message": f"Connexion réussie (databricks:{endpoint})"}
                detail = resp.text[:200] if resp.text else f"HTTP {resp.status_code}"
                return {"ok": False, "message": f"Erreur {resp.status_code}: {detail}"}

            if provider == "openai":
                base_url = str((payload or {}).get("baseUrl") or _os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).strip().rstrip("/")
                target = base_url
                api_key = str((payload or {}).get("token") or _os.environ.get("OPENAI_API_KEY", "")).strip()
                model = str((payload or {}).get("model") or _os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")).strip()
                if not api_key:
                    return {"ok": False, "message": "OPENAI_API_KEY non configuré"}
                resp = _requests.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 5,
                        "temperature": 0,
                    },
                    timeout=15,
                )
                if resp.status_code == 200:
                    return {"ok": True, "message": f"Connexion réussie (openai:{model})"}
                detail = resp.text[:200] if resp.text else f"HTTP {resp.status_code}"
                return {"ok": False, "message": f"Erreur {resp.status_code}: {detail}"}

            if provider == "ollama":
                base_url = str((payload or {}).get("baseUrl") or _os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")).strip().rstrip("/")
                target = base_url
                model = str((payload or {}).get("model") or _os.environ.get("OLLAMA_MODEL", "llama3.1")).strip()
                resp = _requests.post(
                    f"{base_url}/api/chat",
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "stream": False,
                    },
                    timeout=15,
                )
                if resp.status_code == 200:
                    return {"ok": True, "message": f"Connexion réussie (ollama:{model})"}
                detail = resp.text[:200] if resp.text else f"HTTP {resp.status_code}"
                return {"ok": False, "message": f"Erreur {resp.status_code}: {detail}"}

            if provider == "custom":
                base_url = str((payload or {}).get("baseUrl") or _os.environ.get("CUSTOM_LLM_BASE_URL", "")).strip().rstrip("/")
                target = base_url
                chat_path = str((payload or {}).get("chatPath") or _os.environ.get("CUSTOM_LLM_CHAT_PATH", "/v1/chat/completions")).strip()
                model = str((payload or {}).get("model") or _os.environ.get("CUSTOM_LLM_MODEL", "")).strip()
                auth_header = str((payload or {}).get("authHeader") or _os.environ.get("CUSTOM_LLM_AUTH_HEADER", "Authorization")).strip() or "Authorization"
                auth_scheme = str((payload or {}).get("authScheme") or _os.environ.get("CUSTOM_LLM_AUTH_SCHEME", "Bearer")).strip()
                token = str((payload or {}).get("token") or _os.environ.get("CUSTOM_LLM_API_KEY", "")).strip()
                custom_headers_raw = str((payload or {}).get("customHeaders") or _os.environ.get("CUSTOM_LLM_EXTRA_HEADERS", "")).strip()
                if not base_url:
                    return {"ok": False, "message": "CUSTOM_LLM_BASE_URL non configuré"}
                headers = {"Content-Type": "application/json"}
                if token:
                    headers[auth_header] = f"{auth_scheme} {token}".strip()
                headers.update(_parse_custom_headers(custom_headers_raw))
                resp = _requests.post(
                    f"{base_url}{chat_path}",
                    headers=headers,
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 5,
                        "temperature": 0,
                    },
                    timeout=15,
                )
                if resp.status_code == 200:
                    return {"ok": True, "message": "Connexion réussie (custom provider)"}
                detail = resp.text[:200] if resp.text else f"HTTP {resp.status_code}"
                return {"ok": False, "message": f"Erreur {resp.status_code}: {detail}"}

            return {"ok": False, "message": f"Provider non supporté: {provider}"}
        except _requests.exceptions.ConnectionError:
            if target:
                return {"ok": False, "message": f"Impossible de joindre {target}"}
            return {"ok": False, "message": "Impossible de joindre le provider IA"}
        except _requests.exceptions.Timeout:
            return {"ok": False, "message": "Délai d'attente dépassé (15s)"}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    @router.put("/settings/sftp-password")
    def put_sftp_password(payload: dict, req: Request):
        try:
            ensure_admin(req)
        except HTTPException:
            raise
        except Exception:
            pass

        password = str((payload or {}).get("password") or "")
        if not password.strip():
            raise HTTPException(status_code=400, detail="Mot de passe SFTP requis")

        os.environ["SFTP_PASSWORD"] = password
        return {"ok": True, "message": "Mot de passe SFTP mis à jour"}

    @router.put("/settings/databricks-token")
    def put_databricks_token(payload: dict, req: Request):
        try:
            ensure_admin(req)
        except HTTPException:
            raise
        except Exception:
            pass

        token = str((payload or {}).get("token") or "")
        if not token.strip():
            raise HTTPException(status_code=400, detail="Token Databricks requis")

        os.environ["DATABRICKS_TOKEN"] = token
        return {"ok": True, "message": "Token Databricks mis à jour"}

    @router.put("/settings/ai-token")
    def put_ai_token(payload: dict, req: Request):
        try:
            ensure_admin(req)
        except HTTPException:
            raise
        except Exception:
            pass

        provider = str((payload or {}).get("provider") or "").strip().lower()
        token = str((payload or {}).get("token") or "")
        if not token.strip():
            raise HTTPException(status_code=400, detail="Token IA requis")

        if provider == "databricks":
            os.environ["DATABRICKS_TOKEN"] = token
            return {"ok": True, "message": "Token Databricks mis à jour"}
        if provider == "openai":
            os.environ["OPENAI_API_KEY"] = token
            return {"ok": True, "message": "Token OpenAI mis à jour"}
        if provider == "custom":
            os.environ["CUSTOM_LLM_API_KEY"] = token
            return {"ok": True, "message": "Token Custom provider mis à jour"}
        if provider == "ollama":
            return {"ok": True, "message": "Ollama ne nécessite pas de token par défaut"}

        raise HTTPException(status_code=400, detail=f"Provider non supporté: {provider}")

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
        "connectorConfig": {
            "apiBaseUrl": "",
            "dbSyncEnabled": True,
            "csvDelimiter": ";",
            "sftpProfile": "default",
        },
        "masterdataN8nConfig": {
            "enabled": True,
            "webhookUrl": "http://host.docker.internal:5678/webhook/masterdata-sync",
            "authHeader": "x-api-key",
            "timeoutSeconds": 120,
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


def _map_platform_status(status: str | None) -> str:
    m = {
        "REVIEW_REQUIRED": "Revue requise",
        "COMPLETED": "Généré",
        "FAILED": "Rejeté",
        "REJECTED": "Rejeté",
        "PROCESSING": "À revoir",
        "SFTP_FAILED": "SFTP échoué",
    }
    return m.get(status or "", "À revoir")


def _list_combined_orders(actor: str | None = None, role: str | None = None, include_done: bool = False) -> list[dict]:
    """List all orders with optional actor/role context (for future RBAC filtering).
    
    Args:
        actor: Current user identity (email) — passed for PostgreSQL RLS context
        role: Current user role ("admin" or "adv") — passed for PostgreSQL RLS context
    
    Note: SQLite backend ignores actor/role. PostgreSQL backend uses them for RLS.
    """
    store = get_store()
    
    # TODO (Phase 6): Apply RBAC filtering based on actor/role
    # if role == "adv" and actor:
    #     # Filter to orders assigned to this ADV or in their scope
    #     ...
    
    rows = list(store.list_all_orders_summary() if include_done else store.list_orders_summary())
    rows_by_id = {
        str(row.get("order_id") or ""): row
        for row in rows
        if str(row.get("order_id") or "")
    }
    try:
        for conv in engine_bridge.list_conversions(limit=200):
            conv_id = str(conv.get("id") or conv.get("pdf_hash") or "")
            if not conv_id:
                continue
            conv_row = {
                "order_id": conv_id,
                "file_name": conv.get("source_filename") or conv.get("pdf_hash") or "Document sans nom",
                "client_name": conv.get("customer_name"),
                "global_confidence": conv.get("confidence") or 0,
                "status": _map_platform_status(conv.get("status")),
                "created_at": conv.get("created_at"),
                "updated_at": conv.get("updated_at") or conv.get("created_at"),
                "rejection_code": conv.get("rejection_code"),
                "rejection_message": conv.get("rejection_message"),
            }
            existing = rows_by_id.get(conv_id)
            if existing is None or _is_timestamp_newer(
                conv_row.get("updated_at") or conv_row.get("created_at"),
                existing.get("updated_at") or existing.get("created_at"),
            ):
                rows_by_id[conv_id] = conv_row
    except Exception:
        pass
    _DONE_STATUSES = {"Envoyé SAP"}
    rows = list(rows_by_id.values()) if include_done else [r for r in rows_by_id.values() if r.get("status") not in _DONE_STATUSES]
    rows.sort(key=_row_sort_timestamp, reverse=True)
    return rows[:200]


def _row_sort_timestamp(row: dict) -> datetime:
    """Sort mixed SQLite/PostgreSQL timestamp values safely."""
    parsed = _parse_timestamp(row.get("updated_at")) or _parse_timestamp(row.get("created_at"))
    return parsed or datetime.min.replace(tzinfo=timezone.utc)


def _is_timestamp_newer(candidate: str | None, current: str | None) -> bool:
    candidate_dt = _parse_timestamp(candidate)
    current_dt = _parse_timestamp(current)
    if candidate_dt and current_dt:
        return candidate_dt > current_dt
    if candidate_dt:
        return True
    return False


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _to_iso_utc(value: str | None) -> str | None:
    """Normalize mixed timestamp inputs to ISO-8601 UTC for frontend consistency."""
    parsed = _parse_timestamp(value)
    return parsed.isoformat() if parsed else None


def _order_sent_to_sap(order: dict) -> bool:
    status = str(order.get("status") or "").strip()
    if status == "Envoyé SAP":
        return True
    return bool(str(order.get("sapSentAt") or order.get("sap_sent_at") or "").strip())


def _sap_resend_cooldown_seconds() -> int:
    try:
        return max(0, int(os.environ.get("SAP_RESEND_COOLDOWN_SECONDS", "300")))
    except Exception:
        return 300


def _format_cooldown_mmss(seconds: int) -> str:
    total = max(0, int(seconds))
    return f"{total // 60}:{total % 60:02d}"


def _sap_resend_cooldown_info(order: dict) -> dict:
    """Server-side cooldown after a successful SAP send (default 5 minutes)."""
    cooldown = _sap_resend_cooldown_seconds()
    sap_sent_at = order.get("sapSentAt") or order.get("sap_sent_at")
    sent_at = _parse_timestamp(str(sap_sent_at) if sap_sent_at else None)
    if not sent_at or cooldown <= 0:
        return {
            "active": False,
            "remainingSeconds": 0,
            "cooldownSeconds": cooldown,
            "resendAvailableAt": None,
        }
    available_at = sent_at + timedelta(seconds=cooldown)
    remaining = max(0, int((available_at - datetime.now(timezone.utc)).total_seconds()))
    return {
        "active": remaining > 0,
        "remainingSeconds": remaining,
        "cooldownSeconds": cooldown,
        "resendAvailableAt": available_at.isoformat(),
    }


def _with_sap_resend_cooldown(review: dict) -> dict:
    order = dict(review.get("order") or {})
    order["sapResendCooldown"] = _sap_resend_cooldown_info(order)
    return {**review, "order": order}


def _require_mutable_order(order_id: str) -> dict:
    review = get_store().load_order_review(order_id)
    if not review:
        raise HTTPException(404)
    if _order_sent_to_sap(review.get("order") or {}):
        raise HTTPException(
            409,
            "Cette commande a déjà été envoyée vers SAP et ne peut plus être modifiée.",
        )
    return review


def _order_list_item(o: dict) -> dict:
    created_at = _to_iso_utc(o.get("created_at"))
    updated_at = _to_iso_utc(o.get("updated_at"))
    processed_at = _to_iso_utc(o.get("processed_at"))
    sap_sent_at = _to_iso_utc(o.get("sap_sent_at"))
    return {
        "orderId": o["order_id"],
        "fileName": o["file_name"],
        "clientName": o["client_name"] or "—",
        "confidence": int(o.get("global_confidence") or 0),
        "issue": _issue_label(o),
        "date": updated_at or created_at,
        "createdAt": created_at,
        "updatedAt": updated_at,
        "status": o.get("status", "À revoir"),
        "processedAt": sap_sent_at or processed_at,
        "sapSentAt": sap_sent_at,
        "sapSentBy": o.get("sap_sent_by") or None,
        "processedBy": o.get("processed_by") or o.get("uploaded_by"),
        "assignedTo": o.get("assigned_to"),
        "holdReason": o.get("hold_reason"),
        "transferredFrom": o.get("transferred_from"),
        "transferredTo": o.get("transferred_to"),
        "transferNote": o.get("transfer_note"),
        "source": o.get("source") or "unknown",
        "action": None,
    }


def _issue_label(o: dict) -> str:
    if o.get("rejection_message"):
        return o["rejection_message"]
    status = o.get("status") or ""
    if status == "Rejeté":
        return "Commande rejetée par le moteur"
    if status == "Généré":
        return "EDIFACT généré"
    if o.get("global_confidence", 100) < 90:
        return "Confiance insuffisante"
    return "Revue requise"


def _conversion_from_engine(order_id: str, upload_id: str, result: dict, operator: str = "operator") -> dict:
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
        "operator": operator,
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


def _mandatory_review_errors(review: dict) -> list[str]:
    """French validation messages for fields required before EDIFACT generation."""
    errors: list[str] = []
    order = review.get("order") or {}
    partners = review.get("partners") or []
    lines = review.get("lines") or []

    soldto = next((p for p in partners if p.get("partnerFunction") == "soldto"), {})
    shipto = next((p for p in partners if p.get("partnerFunction") == "shipto"), {})

    if not str(order.get("customerOrderNumber") or "").strip():
        errors.append("N° de commande client manquant")
    if not order.get("orderDate"):
        errors.append("Date de commande manquante")
    if not str(soldto.get("partnerCode") or "").strip():
        errors.append("Code sold-to SAP manquant (section Sold-to / AG)")
    if not str(shipto.get("partnerCode") or "").strip():
        errors.append("Code ship-to SAP manquant")
    if not lines:
        errors.append("Aucune ligne de commande — ajoutez au moins une ligne")
    else:
        for ln in lines:
            if not str(ln.get("boschArticle") or "").strip():
                errors.append(f"Ligne {ln.get('lineNumber')} : article Bosch manquant")
            elif not ln.get("quantity"):
                errors.append(f"Ligne {ln.get('lineNumber')} : quantité manquante")

    pending = [
        a for a in (review.get("anomalies") or [])
        if str(a.get("status") or "") in ("Ouverte", "Bloquante")
    ]
    if pending:
        errors.append(
            f"{len(pending)} anomalie(s) en attente — validez ou ignorez chacune avant de valider la commande"
        )
        for anomaly in pending:
            errors.append(f"Anomalie : {anomaly.get('message', '—')}")

    return errors


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
        "lines_from_review": True,
        "soldto_partner": {
            "name": soldto.get("partnerName"),
            "street": soldto.get("addressLine1"),
            "postal_code": soldto.get("postalCode"),
            "city": soldto.get("city"),
            "country": soldto.get("country"),
        },
        "shipto_partner": {
            "name": shipto.get("partnerName"),
            "street": shipto.get("addressLine1"),
            "postal_code": shipto.get("postalCode"),
            "city": shipto.get("city"),
            "country": shipto.get("country"),
            "manually_edited": bool(shipto.get("manuallyEdited")),
        },
        "lines": [
            {
                "line_number": ln.get("lineNumber"),
                "matnr": ln.get("boschArticle"),
                "quantity": ln.get("quantity"),
                "unit": ln.get("unit") or "PCE",
                "unit_price": ln.get("unitPrice"),
                "description": ln.get("designation"),
            }
            for ln in review.get("lines", [])
        ],
    }


def _ensure_conversion_for_generate(order_id: str, review: dict) -> None:
    """Create a conversions row when missing (legacy/demo orders)."""
    engine_bridge.init_db()
    if engine_bridge.load_conversion(order_id):
        return

    o = review["order"]
    soldto = next((p for p in review["partners"] if p["partnerFunction"] == "soldto"), {})
    shipto = next((p for p in review["partners"] if p["partnerFunction"] == "shipto"), {})

    ext: dict = {}
    try:
        conn = get_store()._conn()
        row = conn.execute(
            "SELECT extraction_json FROM file2edi_orders WHERE order_id=?",
            [order_id],
        ).fetchone()
        conn.close()
        if row and row["extraction_json"]:
            ext = json.loads(row["extraction_json"])
    except Exception:
        ext = {}

    if not ext.get("order"):
        ext = _engine_from_conversion(
            {
                "source_filename": o.get("fileName"),
                "pdf_hash": order_id,
                "po_number": o.get("customerOrderNumber"),
                "order_date": o.get("orderDate"),
                "delivery_date": o.get("requestedDeliveryDate"),
                "soldto": soldto.get("partnerCode"),
                "shipto": shipto.get("partnerCode"),
                "customer_name": o.get("clientName"),
                "confidence": o.get("globalConfidence", 0),
            },
            ext if ext else {"lines": {"count": len(review.get("lines", [])), "items": []}},
        )

    ext["pdf_hash"] = order_id
    ext["filename"] = o.get("fileName") or ext.get("filename") or ""
    ext["correlation_id"] = o.get("uploadId")
    ext.setdefault("order", {})
    ext["order"].setdefault("po_number", o.get("customerOrderNumber"))
    ext["order"].setdefault("order_date", o.get("orderDate"))
    ext["order"].setdefault("delivery_date", o.get("requestedDeliveryDate"))
    ext.setdefault("customer", {})
    ext["customer"].setdefault("soldto", soldto.get("partnerCode"))
    ext["customer"].setdefault("shipto", shipto.get("partnerCode"))
    ext["customer"].setdefault("name", o.get("clientName"))
    ext.setdefault("lines", {"count": len(review.get("lines", [])), "items": []})
    ext.setdefault("rejection", {"decision": "REVIEW_REQUIRED"})
    ext.setdefault("edifact", {"generated": False})

    engine_bridge.upsert_conversion(ext)


def _extract_generate_errors(result: dict) -> list[str]:
    blockers = result.get("blockers")
    if isinstance(blockers, list) and blockers:
        return [
            b.get("message") or b.get("code") or str(b)
            for b in blockers
            if isinstance(b, dict)
        ]
    msg = result.get("message") or result.get("error")
    if msg:
        return [str(msg)]
    return ["Génération échouée"]
