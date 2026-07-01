"""EDIFACT Generator -- Gradio web application.

Bosch Thermotechnologie France / ELM_STANDARD D.96A
Converts customer PDF purchase orders -> EDIFACT .tst files.
AI OCR validation powered by databricks-gpt-oss-120b.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

# Engine path injection
EDIFACT_ROOT = "/Workspace/Users/rsr1dy@bosch.com/EDIFACT"
sys.path.insert(0, EDIFACT_ROOT)
sys.path.insert(0, os.path.join(EDIFACT_ROOT, "src"))

# Clear Jupyter env-vars so Gradio does NOT enter non-blocking notebook mode
for _jvar in ("JPY_PARENT_PID", "JPY_SESSION_NAME", "JPY_INTERRUPT_EVENT",
               "JUPYTER_SERVER_ROOT", "KERNEL_ID"):
    os.environ.pop(_jvar, None)

try:
    import gradio as gr
except ImportError as _err:
    raise SystemExit(f"[EDIFACT-APP] gradio not installed: {_err}") from _err

# ── Constants ──────────────────────────────────────────────────────────────────
MASTER_DATA_DIR   = "/Workspace/Users/rsr1dy@bosch.com/masterdata"
DB_PATH           = os.path.join(EDIFACT_ROOT, "data", "edifact_standalone.db")
CONFIG_INI        = os.path.join(EDIFACT_ROOT, "config.ini")
DATABRICKS_HOST   = os.environ.get("DATABRICKS_HOST",
                        "https://adb-5555213114570927.7.azuredatabricks.net")
AI_ENDPOINT_URL   = (
    f"{DATABRICKS_HOST.rstrip('/')}"
    "/serving-endpoints/databricks-gpt-oss-120b/invocations"
)
MASTER_FILES = [
    ("Customers",    "10564_Customers.csv"),
    ("Partners",     "10564_Partners.csv"),
    ("Materials",    "10564_Materials.csv"),
    ("Sales Orders", "DB_Salesorder.csv"),
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve_upload(pdf_file) -> str:
    """Return filesystem path of a Gradio-uploaded file (all 4.x variants)."""
    if pdf_file is None:
        return ""
    if hasattr(pdf_file, "name"):
        return pdf_file.name
    if isinstance(pdf_file, dict):
        return pdf_file.get("path", pdf_file.get("name", ""))
    return str(pdf_file)


def _get_token() -> str:
    """Return the Databricks OAuth token available in the App environment."""
    return os.environ.get("DATABRICKS_TOKEN", "")


# ── AI validation ──────────────────────────────────────────────────────────────

AI_SYSTEM_PROMPT = """\
You are an EDIFACT D.96A ORDERS validator for Bosch Thermotechnologie France (ELM_STANDARD).
Given an EDIFACT message, perform the following checks and report each as PASS or FAIL:

1. UNB sender GLN = 4399901876613
2. UNB receiver GLN = 3015981600108
3. BGM segment present (purchase order qualifier 220)
4. DTM+137 (order date) present and valid format CCYYMMDD
5. DTM+2 (delivery date) present and valid
6. NAD+BY (buyer) present with correct GLN
7. NAD+DP (delivery point) present
8. LIN segments present (at least one order line)
9. No freight/tax-only lines (PORT, ECOTAXE, FRAIS DE PORT)
10. UNT segment count matches actual segment count

Return a concise table: Check | Result | Note
Then a one-line OVERALL: VALID or INVALID.
"""


def ai_validate_edifact(edifact_text: str) -> str:
    """Send EDIFACT text to the LLM endpoint for structural validation."""
    import json as _json
    try:
        import requests as _req
    except ImportError:
        return "requests library not installed"

    if not edifact_text.strip():
        return "No EDIFACT content to validate."

    token = _get_token()
    if not token:
        return "DATABRICKS_TOKEN not set -- app service principal token unavailable."

    payload = {
        "messages": [
            {"role": "system", "content": AI_SYSTEM_PROMPT},
            {"role": "user",   "content": f"Validate this EDIFACT message:\n\n{edifact_text[:3000]}"},
        ],
        "max_tokens": 700,
        "temperature": 0,
    }
    try:
        resp = _req.post(
            AI_ENDPOINT_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
            },
            json=payload,
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        return f"AI call failed: {type(exc).__name__}: {exc}"


def ai_extract_po(raw_text: str) -> str:
    """Ask the LLM to extract key PO fields from raw PDF text."""
    import json as _json
    try:
        import requests as _req
    except ImportError:
        return "requests library not installed"

    if not raw_text.strip():
        return "No text provided."

    token = _get_token()
    if not token:
        return "DATABRICKS_TOKEN not set."

    extract_prompt = """\
You are an EDI assistant for Bosch Thermotechnologie France.
Extract the following fields from the raw purchase order text and return JSON:
{
  "po_number": "...",
  "order_date": "YYYY-MM-DD or null",
  "delivery_date": "YYYY-MM-DD or null",
  "buyer_name": "...",
  "delivery_address": "...",
  "lines": [
    {"line_no": 1, "article_code": "...", "description": "...", "qty": 0, "unit_price": 0.0}
  ]
}
Return only valid JSON, no explanation.
"""
    payload = {
        "messages": [
            {"role": "system", "content": extract_prompt},
            {"role": "user",   "content": raw_text[:4000]},
        ],
        "max_tokens": 800,
        "temperature": 0,
    }
    try:
        resp = _req.post(
            AI_ENDPOINT_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
            },
            json=payload,
            timeout=45,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        return f"AI call failed: {type(exc).__name__}: {exc}"


# ── EDIFACT conversion ─────────────────────────────────────────────────────────

def convert_pdf(pdf_file, send_sftp: bool):
    """Convert an uploaded PDF PO into an EDIFACT .tst file."""
    if pdf_file is None:
        return gr.update(visible=False), "", "", "No PDF uploaded."
    try:
        from src.config_loader import load_config              # type: ignore
        from src.edifact_orders_engine import EdifactOrdersEngine  # type: ignore
        cfg    = load_config(CONFIG_INI)
        engine = EdifactOrdersEngine(cfg)

        src_path = _resolve_upload(pdf_file)
        if not src_path or not os.path.exists(src_path):
            return gr.update(visible=False), "", "", "Uploaded file not found."
        pdf_name = os.path.basename(src_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / pdf_name
            shutil.copy(src_path, str(pdf_path))
            result = engine.process_file(str(pdf_path))

        if result.get("status") == "success":
            tst_content: str = result.get("edifact_content") or ""
            tst_filename = Path(pdf_name).stem + ".tst"
            tst_path = os.path.join(tempfile.gettempdir(), tst_filename)
            with open(tst_path, "w", encoding="utf-8") as fh:
                fh.write(tst_content)
            line_count = len(tst_content.splitlines())
            if send_sftp:
                try:
                    from src.sftp_delivery import SftpDelivery  # type: ignore
                    SftpDelivery(cfg).deliver(tst_path)
                    status = f"[OK] {tst_filename} -- {line_count} segments (SFTP sent)"
                except Exception as sftp_err:
                    status = f"[OK] {tst_filename} -- {line_count} segments (SFTP error: {sftp_err})"
            else:
                status = f"[OK] {tst_filename} -- {line_count} segments"
            return gr.update(value=tst_path, visible=True), tst_content[:4000], tst_content, status
        else:
            reason = result.get("rejection_reason") or result.get("reason") or "Unknown"
            return gr.update(visible=False), "", "", f"[REJECTED] {reason}"
    except Exception as exc:
        return gr.update(visible=False), "", "", f"[ERROR] {type(exc).__name__}: {exc}"


# ── History / master data / SFTP ───────────────────────────────────────────────

def load_history() -> list:
    if not os.path.exists(DB_PATH):
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute(
            "SELECT id, filename, status, po_number, soldto, created_at, rejection_reason "
            "FROM jobs ORDER BY created_at DESC LIMIT 100"
        )
        rows = [list(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as exc:
        return [["-", "-", f"DB error: {exc}", "-", "-", "-", "-"]]


def reload_master_data() -> list:
    rows = []
    for label, fname in MASTER_FILES:
        fpath = os.path.join(MASTER_DATA_DIR, fname)
        if not os.path.exists(fpath):
            rows.append([label, fname, 0, "Missing"]); continue
        try:
            import pandas as pd
            pd.read_csv(fpath, sep=";", encoding="utf-8-sig", nrows=0)
            with open(fpath, "r", encoding="utf-8-sig", errors="replace") as fh:
                row_count = sum(1 for _ in fh) - 1
            rows.append([label, fname, row_count, "OK"])
        except Exception as exc:
            rows.append([label, fname, 0, f"Error: {exc}"])
    return rows


def test_sftp() -> str:
    host = os.environ.get("SFTP_HOST", "")
    user = os.environ.get("SFTP_USERNAME", "")
    pwd  = os.environ.get("SFTP_PASSWORD", "")
    if not host or not user:
        return "SFTP_HOST / SFTP_USERNAME not set"
    try:
        import paramiko
        t = paramiko.Transport((host, 22))
        t.connect(username=user, password=pwd)
        paramiko.SFTPClient.from_transport(t).close()
        t.close()
        return f"Connected to {host}"
    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


# ── Gradio UI ──────────────────────────────────────────────────────────────────
with gr.Blocks(
    title="EDIFACT Generator -- Bosch HC SFR-BI",
    theme=gr.themes.Soft(),
    css="""
        #edifact-preview textarea { font-family: 'Courier New', monospace; font-size: 12px; }
        #ai-report textarea        { font-family: 'Courier New', monospace; font-size: 12px; }
        .status-ok   { color: #2d7d2d; font-weight: bold; }
        .status-fail { color: #cc0000; font-weight: bold; }
    """,
) as demo:

    gr.Markdown(
        "# EDIFACT Orders Generator\n"
        "**Bosch Thermotechnologie France -- ELM_STANDARD D.96A**"
    )

    # Hidden state: full EDIFACT content shared between tabs
    _edifact_state = gr.State("")

    with gr.Tabs():

        # ── Tab 1: Convert PDF ─────────────────────────────────────────────────
        with gr.TabItem("Convert PDF"):
            with gr.Row():
                with gr.Column(scale=1):
                    pdf_input    = gr.File(label="Purchase Order PDF", file_types=[".pdf"])
                    send_sftp_cb = gr.Checkbox(label="Send to SFTP after conversion", value=False)
                    convert_btn  = gr.Button("Convert", variant="primary", size="lg")

                with gr.Column(scale=2):
                    status_out   = gr.Textbox(label="Status", interactive=False, lines=2)
                    preview_out  = gr.Textbox(
                        label="EDIFACT Preview (first 4000 chars)",
                        lines=18, interactive=False, elem_id="edifact-preview",
                    )
                    with gr.Row():
                        download_out   = gr.File(label="Download .tst", visible=False)
                        ai_validate_btn = gr.Button("AI Validate", variant="secondary")
                    ai_report_out = gr.Textbox(
                        label="AI Validation Report",
                        lines=10, interactive=False, elem_id="ai-report",
                        placeholder="Click 'AI Validate' after conversion to check the EDIFACT message...",
                    )

            convert_btn.click(
                fn=convert_pdf,
                inputs=[pdf_input, send_sftp_cb],
                outputs=[download_out, preview_out, _edifact_state, status_out],
            )
            ai_validate_btn.click(
                fn=ai_validate_edifact,
                inputs=[_edifact_state],
                outputs=[ai_report_out],
            )

        # ── Tab 2: AI Extraction ───────────────────────────────────────────────
        with gr.TabItem("AI Extract"):
            gr.Markdown("### Extract PO fields from raw text using LLM\n"
                        "Paste raw PDF text or extracted OCR content below:")
            with gr.Row():
                with gr.Column(scale=1):
                    raw_text_in  = gr.Textbox(label="Raw PO Text", lines=15,
                                               placeholder="Paste raw text from PDF...")
                    extract_btn  = gr.Button("Extract Fields (AI)", variant="primary")
                with gr.Column(scale=1):
                    extract_out  = gr.Textbox(label="Extracted JSON", lines=15,
                                               interactive=False, elem_id="ai-report")
            extract_btn.click(
                fn=ai_extract_po,
                inputs=[raw_text_in],
                outputs=[extract_out],
            )

        # ── Tab 3: Job History ─────────────────────────────────────────────────
        with gr.TabItem("Job History"):
            refresh_hist_btn = gr.Button("Refresh")
            history_df = gr.Dataframe(
                headers=["ID","Filename","Status","PO Number","Sold-To","Created At","Rejection Reason"],
                interactive=False, wrap=True,
            )
            refresh_hist_btn.click(fn=load_history, outputs=history_df)

        # ── Tab 4: Master Data ─────────────────────────────────────────────────
        with gr.TabItem("Master Data"):
            refresh_md_btn = gr.Button("Reload Stats")
            master_df = gr.Dataframe(
                headers=["Dataset","File","Rows","Status"],
                interactive=False,
            )
            refresh_md_btn.click(fn=reload_master_data, outputs=master_df)

        # ── Tab 5: Settings ────────────────────────────────────────────────────
        with gr.TabItem("Settings"):
            with gr.Row():
                gr.Textbox(label="SFTP_HOST",       value=os.environ.get("SFTP_HOST","(not set)"),       interactive=False)
                gr.Textbox(label="SFTP_USERNAME",   value=os.environ.get("SFTP_USERNAME","(not set)"),   interactive=False)
                gr.Textbox(label="SFTP_REMOTE_DIR", value=os.environ.get("SFTP_REMOTE_DIR","(not set)"), interactive=False)
            with gr.Row():
                _sftp_btn = gr.Button("Test SFTP Connection")
                _sftp_out = gr.Textbox(label="Result", interactive=False)
            _sftp_btn.click(fn=test_sftp, outputs=_sftp_out)

            gr.Markdown(f"""
### UNB Profile
- Sender GLN: 4399901876613
- Receiver GLN: 3015981600108
- Profile: ELM_STANDARD (UNOC:3)

### AI Endpoint
- Model: databricks-gpt-oss-120b
- URL: {AI_ENDPOINT_URL}
- Token: {"set" if _get_token() else "NOT SET (DATABRICKS_TOKEN missing)"}

### Paths
- Master Data: {MASTER_DATA_DIR}
- Engine: {EDIFACT_ROOT}
""")


# ── Launch ─────────────────────────────────────────────────────────────────────
# prevent_thread_lock=True + threading.Event().wait() keeps the process alive
# even if Gradio's IPython/Jupyter detection would otherwise return immediately.
if __name__ == "__main__" or True:
    _port       = int(os.environ.get("DATABRICKS_APP_PORT", 8080))
    _keep_alive = threading.Event()
    print(f"[EDIFACT-APP] Starting Gradio on 0.0.0.0:{_port}", flush=True)
    try:
        demo.launch(
            server_port=_port,
            server_name="0.0.0.0",
            show_api=False,
            share=False,
            prevent_thread_lock=True,
        )
        print("[EDIFACT-APP] Server started -- blocking on keep-alive.", flush=True)
        _keep_alive.wait()   # block forever
    except KeyboardInterrupt:
        print("[EDIFACT-APP] Shutting down.", flush=True)
    except Exception as _e:
        import traceback as _tb
        print(f"[EDIFACT-APP] Error: {_e}", flush=True)
        _tb.print_exc()
        raise
