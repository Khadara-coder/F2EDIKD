"""
FILE2EDI API v2.1 - PDF to EDIFACT D96A

Production-ready API with:
- Single response format (always JSON with status field)
- Idempotency via PDF hash (no duplicate EDIFACT generation)
- Multipart upload AND base64 JSON input
- Auto-generated OpenAPI docs at /docs
"""
from __future__ import annotations

import base64
import hashlib
import os
import sys
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("LOCATEANYTHING_PROJECT_ROOT", str(APP_DIR))
os.environ.setdefault("MASTER_DATA_DIR", str(APP_DIR / "data" / "masterdata"))
os.environ.setdefault("EMBEDDING_MODEL_DIR", str(APP_DIR / "all-MiniLM-L6-v2"))
os.environ.setdefault("TESSERACT_LANG", "eng")


# ---------------------------------------------------------------------------
# Cache (LRU idempotency based on PDF hash)
# ---------------------------------------------------------------------------
class LRUCache(OrderedDict):
    def __init__(self, maxsize: int = 200):
        super().__init__()
        self.maxsize = maxsize

    def get_or_none(self, key: str) -> Optional[dict]:
        if key in self:
            self.move_to_end(key)
            return self[key]
        return None

    def put(self, key: str, value: dict):
        self[key] = value
        self.move_to_end(key)
        if len(self) > self.maxsize:
            self.popitem(last=False)


result_cache = LRUCache(maxsize=200)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load masterdata at startup."""
    from app.masterdata import get_master_data
    t0 = time.time()
    get_master_data()
    app.state.master_data_loaded = True
    app.state.startup_time = time.time() - t0
    app.state.requests_processed = 0
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="FILE2EDI",
    description="""
## PDF Purchase Order to EDIFACT D96A Converter

Upload a PDF purchase order (multipart or base64) and receive:
- Structured extraction (PO number, dates, customer, line items)
- SOLDTO/SHIPTO resolution against SAP masterdata
- Rejection analysis (9 Esker rules)
- EDIFACT D96A message ready for SAP AS2 transmission

### Authentication
Use OAuth2 token exchange with your Databricks PAT or Service Principal.

### Idempotency
Same PDF (by SHA-256 hash) returns cached result without reprocessing.
""",
    version="2.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class Base64Request(BaseModel):
    """Alternative input: PDF as base64-encoded string."""
    filename: str = Field(..., description="Original PDF filename", examples=["commande_001.pdf"])
    content_base64: str = Field(..., description="PDF file content encoded in base64")


class OrderInfo(BaseModel):
    po_number: Optional[str] = None
    order_date: Optional[str] = None
    delivery_date: Optional[str] = None


class AddressInfo(BaseModel):
    street: str = ""
    postal_code: str = ""
    city: str = ""
    country: str = "FR"


class DetectedAddressInfo(BaseModel):
    name: str = ""
    street: str = ""
    postal_code: str = ""
    city: str = ""
    raw: str = ""
    statut: str = ""


class CustomerInfo(BaseModel):
    soldto: Optional[str] = None
    shipto: Optional[str] = None
    name: Optional[str] = None
    confidence: int = 0
    soldto_confidence: int = 0
    shipto_confidence: int = 0
    shipto_score: int = 0
    delivery_address: AddressInfo = AddressInfo()
    detected_address: DetectedAddressInfo = DetectedAddressInfo()
    disambiguation: str = ""
    disambiguation_explanation: str = ""
    reason_codes: list[str] = []
    matched_by: list[str] = []
    scoring_decision: str = ""


class LineItem(BaseModel):
    numero_ligne: Optional[str] = None
    code_article: Optional[str] = None
    description: Optional[str] = None
    quantite: Optional[Any] = None
    prix_unitaire_ht: Optional[Any] = None
    date_livraison: Optional[str] = None


class LinesInfo(BaseModel):
    count: int = 0
    items: list[dict] = []


class RejectionItem(BaseModel):
    code: str = Field(..., description="Rule code (e.g. NO_DELIVERY_ADDRESS)")
    message: str = Field(..., description="Human-readable rejection reason")
    severity: str = Field(..., description="blocking or warning")
    details: dict = {}


class RejectionInfo(BaseModel):
    decision: Optional[str] = Field(None, description="ACCEPTED, REVIEW, or REJECTED")
    reason: Optional[str] = Field(None, description="Primary blocking reason code")
    blocking_count: int = 0
    warning_count: int = 0
    details: list[dict] = Field([], description="List of all rejection rules triggered")


class EdifactInfo(BaseModel):
    generated: bool = False
    message: Optional[str] = None
    warnings: list[str] = []
    errors: Optional[list[str]] = None


class ExtractResponse(BaseModel):
    """Unified response format - always returned, even on processing errors."""
    status: str = Field(..., description="OK | ERROR", examples=["OK"])
    filename: str
    pdf_hash: str = Field(..., description="SHA-256 hash for idempotency")
    cached: bool = Field(False, description="True if result served from cache")
    processing_time_s: float = 0.0
    order: OrderInfo = OrderInfo()
    customer: CustomerInfo = CustomerInfo()
    lines: LinesInfo = LinesInfo()
    rejection: RejectionInfo = RejectionInfo()
    edifact: EdifactInfo = EdifactInfo()
    error: Optional[str] = Field(None, description="Error message if status=ERROR")


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------
def compute_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def process_pdf(payload: bytes, filename: str) -> dict[str, Any]:
    """Run full extraction + EDIFACT pipeline on a single PDF."""
    from app.pdf_reader import pdf_pages_to_text
    from app.extraction import extract_candidate_fields

    text_pages = pdf_pages_to_text(payload, "1")
    if not text_pages:
        raise ValueError("Could not extract text from PDF")

    text = text_pages[0]["text"]
    layout = text_pages[0].get("layout")

    fields = extract_candidate_fields(text, "", filename, layout, {})
    return fields.get("structured", {})


def _build_raw_address(addr: dict) -> str:
    """Build a readable address string from available keys."""
    parts = []
    for key in ["Nom", "Rue", "Code postal", "Ville"]:
        val = addr.get(key)
        if val and str(val).strip():
            parts.append(str(val).strip())
    return ", ".join(parts)


def build_response(structured: dict, filename: str, pdf_hash: str, elapsed: float, cached: bool = False) -> dict:
    """Build unified response from structured extraction result."""
    doc = structured.get("document", {})
    adr = structured.get("adresses", {}).get("Adresse de livraison validee", {})
    detected = structured.get("adresses", {}).get("Adresse de livraison detectee", {})
    rej = structured.get("rejets", {})
    edi = structured.get("edifact", {})
    lignes = structured.get("lignes_commande", {})

    return {
        "status": "OK",
        "filename": filename,
        "pdf_hash": pdf_hash,
        "cached": cached,
        "processing_time_s": round(elapsed, 1),
        "order": {
            "po_number": doc.get("Numero de commande"),
            "order_date": doc.get("Date commande LLM"),
            "delivery_date": doc.get("Date livraison souhaitee"),
        },
        "customer": {
            "soldto": adr.get("SOLDTO"),
            "shipto": adr.get("SHIPTO"),
            "name": adr.get("Nom"),
            "confidence": adr.get("Confiance", 0),
            "delivery_address": {
                "street": adr.get("Rue") or adr.get("Adresse", ""),
                "postal_code": adr.get("Code postal", ""),
                "city": adr.get("Ville", ""),
                "country": "FR",
            },
            "disambiguation": adr.get("Disambiguation", ""),
            "disambiguation_explanation": adr.get("Disambiguation_explanation", ""),
            "reason_codes": adr.get("reason_codes", []),
            "matched_by": adr.get("matched_by", []),
            "shipto_score": adr.get("shipto_score", 0),
            "scoring_decision": adr.get("scoring_decision", ""),
            "soldto_confidence": 90 if adr.get("SOLDTO") != adr.get("SHIPTO") else adr.get("Confiance", 0),
            "shipto_confidence": adr.get("Confiance", 0),
            "detected_address": {
                "name": detected.get("Nom", "") or adr.get("Nom", "") or "",
                "street": detected.get("Rue", "") or adr.get("Rue", "") or "",
                "postal_code": detected.get("Code postal", "") or adr.get("Code postal", "") or "",
                "city": detected.get("Ville", "") or adr.get("Ville", "") or "",
                "raw": detected.get("Adresse complete", "") or _build_raw_address(detected) or _build_raw_address(adr),
                "statut": detected.get("Statut", "") if (detected.get("Rue") or detected.get("Code postal")) else (adr.get("Disambiguation", "") or detected.get("Statut", "")),
            },
        },
        "lines": {
            "count": lignes.get("nb_lignes", 0),
            "items": lignes.get("lignes", []),
        },
        "rejection": {
            "decision": rej.get("decision"),
            "reason": rej.get("primary_reason"),
            "blocking_count": rej.get("blocking_count", 0),
            "warning_count": rej.get("warning_count", 0),
            "details": rej.get("rejections", []),
        },
        "edifact": {
            "generated": edi.get("generated", False),
            "message": edi.get("message"),
            "warnings": edi.get("warnings", []),
            "errors": edi.get("errors"),
        },
        "error": None,
    }


def process_and_respond(payload: bytes, filename: str) -> dict:
    """Process PDF with caching. Returns unified response dict."""
    pdf_hash = compute_hash(payload)

    # Check cache (idempotency)
    cached = result_cache.get_or_none(pdf_hash)
    if cached is not None:
        cached["cached"] = True
        cached["processing_time_s"] = 0.0
        return cached

    # Process
    t0 = time.time()
    try:
        structured = process_pdf(payload, filename)
        response = build_response(structured, filename, pdf_hash, time.time() - t0)
    except Exception as e:
        response = {
            "status": "ERROR",
            "filename": filename,
            "pdf_hash": pdf_hash,
            "cached": False,
            "processing_time_s": round(time.time() - t0, 1),
            "order": {"po_number": None, "order_date": None, "delivery_date": None},
            "customer": {"soldto": None, "shipto": None, "name": None, "confidence": 0, "delivery_address": {"street": "", "postal_code": "", "city": "", "country": ""}, "detected_address": {"name": "", "street": "", "postal_code": "", "city": "", "raw": ""}},
            "lines": {"count": 0, "items": []},
            "rejection": {"decision": None, "reason": None, "blocking_count": 0, "warning_count": 0, "details": []},
            "edifact": {"generated": False, "message": None, "warnings": [], "errors": None},
            "error": str(e),
        }

    # Cache successful results
    if response["status"] == "OK":
        result_cache.put(pdf_hash, response.copy())

    app.state.requests_processed = getattr(app.state, "requests_processed", 0) + 1
    return response


# ---------------------------------------------------------------------------
# Exception handler (never return raw 500)
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "status": "ERROR",
            "filename": "",
            "pdf_hash": "",
            "cached": False,
            "processing_time_s": 0.0,
            "order": {"po_number": None, "order_date": None, "delivery_date": None},
            "customer": {"soldto": None, "shipto": None, "name": None, "confidence": 0, "delivery_address": {"street": "", "postal_code": "", "city": "", "country": ""}, "detected_address": {"name": "", "street": "", "postal_code": "", "city": "", "raw": ""}},
            "lines": {"count": 0, "items": []},
            "rejection": {"decision": None, "reason": None, "blocking_count": 0, "warning_count": 0, "details": []},
            "edifact": {"generated": False, "message": None, "warnings": [], "errors": None},
            "error": f"Internal server error: {type(exc).__name__}: {exc}",
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health", tags=["System"])
async def health():
    """Health check — confirms API and masterdata status."""
    return {
        "status": "ok",
        "version": "2.1.0",
        "master_data_loaded": getattr(app.state, "master_data_loaded", False),
        "startup_time_s": round(getattr(app.state, "startup_time", 0), 1),
        "requests_processed": getattr(app.state, "requests_processed", 0),
        "cache_size": len(result_cache),
    }



# --- MEMO ENDPOINTS (LLM-maintained knowledge base) ---

@app.get("/api/memo", tags=["Memo"])
async def get_memo_content():
    """Read the current memo content."""
    from app.memo import get_memo
    return {"memo": get_memo()}


@app.get("/api/memo/search", tags=["Memo"])
async def search_memo_api(q: str = ""):
    """Search the memo for relevant entries."""
    from app.memo import search_memo
    if not q:
        return {"results": "", "query": ""}
    return {"results": search_memo(q), "query": q}


@app.post("/api/memo/update", tags=["Memo"])
async def update_memo_api(request: dict):
    """Add entry to memo. Body: {"entry": "...", "section": "..."}"""
    from app.memo import update_memo
    entry = request.get("entry", "")
    section = request.get("section", "Cas detectes automatiquement")
    if not entry:
        return {"success": False, "error": "entry is required"}
    return {"success": update_memo(entry, section)}


@app.post("/api/memo/learn", tags=["Memo"])
async def memo_learn(request: dict):
    """Learn from validated resolution. Body: {soldto, shipto, client_name, postal, city, notes}"""
    from app.memo import update_memo
    import datetime
    client = request.get("client_name", "unknown")
    entry = (
        f"### {client} (appris le {datetime.date.today().isoformat()})\n"
        f"- SOLDTO: {request.get('soldto', '')} -> SHIPTO: {request.get('shipto', '')}\n"
        f"- Adresse: {request.get('postal', '')} {request.get('city', '')}\n"
        f"- Methode: {request.get('resolution_method', 'manual')}"
    )
    notes = request.get("notes", "")
    if notes:
        entry += f"\n- Notes: {notes}"
    return {"success": update_memo(entry, "Cas detectes automatiquement"), "entry": entry}

@app.post(
    "/api/extract",
    response_model=ExtractResponse,
    tags=["Extraction"],
    summary="Extract order data and generate EDIFACT from PDF (multipart upload)",
    responses={
        200: {"description": "Extraction complete (check rejection.decision for ACCEPTED/REVIEW/REJECTED)"},
        400: {"description": "Invalid input (not a PDF, empty file)"},
        401: {"description": "Authentication required"},
    },
)
async def extract_multipart(file: UploadFile = File(..., description="PDF purchase order file")):
    """
    Upload a PDF purchase order via multipart form-data.

    The response always has the same JSON structure:
    - `status`: "OK" or "ERROR"
    - `rejection.decision`: "ACCEPTED", "REVIEW", or "REJECTED"
    - `edifact.generated`: true if EDIFACT D96A was produced
    - `pdf_hash`: SHA-256 for idempotency (same PDF = same result from cache)
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return JSONResponse(status_code=400, content={
            "status": "ERROR", "filename": file.filename or "", "pdf_hash": "", "cached": False,
            "processing_time_s": 0.0,
            "order": {"po_number": None, "order_date": None, "delivery_date": None},
            "customer": {"soldto": None, "shipto": None, "name": None, "confidence": 0, "delivery_address": {"street": "", "postal_code": "", "city": "", "country": ""}, "detected_address": {"name": "", "street": "", "postal_code": "", "city": "", "raw": ""}},
            "lines": {"count": 0, "items": []},
            "rejection": {"decision": None, "reason": None, "blocking_count": 0, "warning_count": 0, "details": []},
            "edifact": {"generated": False, "message": None, "warnings": [], "errors": None},
            "error": "Only PDF files accepted (filename must end with .pdf)",
        })

    payload = await file.read()
    if not payload:
        return JSONResponse(status_code=400, content={
            "status": "ERROR", "filename": file.filename, "pdf_hash": "", "cached": False,
            "processing_time_s": 0.0,
            "order": {"po_number": None, "order_date": None, "delivery_date": None},
            "customer": {"soldto": None, "shipto": None, "name": None, "confidence": 0, "delivery_address": {"street": "", "postal_code": "", "city": "", "country": ""}, "detected_address": {"name": "", "street": "", "postal_code": "", "city": "", "raw": ""}},
            "lines": {"count": 0, "items": []},
            "rejection": {"decision": None, "reason": None, "blocking_count": 0, "warning_count": 0, "details": []},
            "edifact": {"generated": False, "message": None, "warnings": [], "errors": None},
            "error": "Empty file",
        })

    return process_and_respond(payload, file.filename)


@app.post(
    "/api/extract/base64",
    response_model=ExtractResponse,
    tags=["Extraction"],
    summary="Extract order data and generate EDIFACT from PDF (base64 JSON)",
    responses={
        200: {"description": "Extraction complete"},
        400: {"description": "Invalid input"},
    },
)
async def extract_base64(body: Base64Request):
    """
    Submit a PDF as a base64-encoded JSON payload.

    Useful for clients that cannot send multipart (e.g., some workflow engines).

    ```json
    {
        "filename": "commande_001.pdf",
        "content_base64": "JVBERi0xLjQK..."
    }
    ```
    """
    if not body.filename.lower().endswith(".pdf"):
        return JSONResponse(status_code=400, content={
            "status": "ERROR", "filename": body.filename, "pdf_hash": "", "cached": False,
            "processing_time_s": 0.0,
            "order": {"po_number": None, "order_date": None, "delivery_date": None},
            "customer": {"soldto": None, "shipto": None, "name": None, "confidence": 0, "delivery_address": {"street": "", "postal_code": "", "city": "", "country": ""}, "detected_address": {"name": "", "street": "", "postal_code": "", "city": "", "raw": ""}},
            "lines": {"count": 0, "items": []},
            "rejection": {"decision": None, "reason": None, "blocking_count": 0, "warning_count": 0, "details": []},
            "edifact": {"generated": False, "message": None, "warnings": [], "errors": None},
            "error": "Filename must end with .pdf",
        })

    try:
        payload = base64.b64decode(body.content_base64)
    except Exception:
        return JSONResponse(status_code=400, content={
            "status": "ERROR", "filename": body.filename, "pdf_hash": "", "cached": False,
            "processing_time_s": 0.0,
            "order": {"po_number": None, "order_date": None, "delivery_date": None},
            "customer": {"soldto": None, "shipto": None, "name": None, "confidence": 0, "delivery_address": {"street": "", "postal_code": "", "city": "", "country": ""}, "detected_address": {"name": "", "street": "", "postal_code": "", "city": "", "raw": ""}},
            "lines": {"count": 0, "items": []},
            "rejection": {"decision": None, "reason": None, "blocking_count": 0, "warning_count": 0, "details": []},
            "edifact": {"generated": False, "message": None, "warnings": [], "errors": None},
            "error": "Invalid base64 content",
        })

    if not payload:
        return JSONResponse(status_code=400, content={
            "status": "ERROR", "filename": body.filename, "pdf_hash": "", "cached": False,
            "processing_time_s": 0.0,
            "order": {"po_number": None, "order_date": None, "delivery_date": None},
            "customer": {"soldto": None, "shipto": None, "name": None, "confidence": 0, "delivery_address": {"street": "", "postal_code": "", "city": "", "country": ""}, "detected_address": {"name": "", "street": "", "postal_code": "", "city": "", "raw": ""}},
            "lines": {"count": 0, "items": []},
            "rejection": {"decision": None, "reason": None, "blocking_count": 0, "warning_count": 0, "details": []},
            "edifact": {"generated": False, "message": None, "warnings": [], "errors": None},
            "error": "Empty file content after base64 decode",
        })

    return process_and_respond(payload, body.filename)


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
STATIC_DIR = APP_DIR / "static"


@app.get("/", include_in_schema=False)
async def root():
    """Serve the drag-and-drop frontend."""
    return FileResponse(str(STATIC_DIR / "index.html"))


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
