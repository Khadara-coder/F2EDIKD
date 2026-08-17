from __future__ import annotations

from PIL import Image

import app.ocr as ocr_mod
from app.ocr import ocr_image_with_layout
from app.pdf_extract import extract_page_with_selective_ocr
from app.pdf_reader import pdf_pages_to_text


def _blank_image() -> Image.Image:
    return Image.new("RGB", (80, 80), "white")


def _native_order_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                "ELM LEBLANC / BOSCH",
                "BON DE COMMANDE FOURNISSEUR DUPLICATA",
                "N 167658",
                "Date 15/02/2024",
                "Client 135156",
                "7736504816 LC 9-4 PVHYB PIECE 7 PCE",
                "Montant HT 3495 EUR",
                "Depot MONDEVILLE PIECES EXPRESS",
            ]
        ),
    )
    payload = doc.tobytes()
    doc.close()
    return payload


def _crash_ocr(_image):
    raise AttributeError("'NoneType' object has no attribute 'TesseractError'")


def test_ocr_image_with_layout_without_pytesseract(monkeypatch):
    monkeypatch.setattr(ocr_mod, "pytesseract", None)
    monkeypatch.setattr(ocr_mod, "_PYTESSERACT_AVAILABLE", False)
    result = ocr_image_with_layout(_blank_image())
    assert result["text"] == ""
    assert result["layout"]["source"] == "ocr_unavailable"
    assert result["layout"]["lines"] == []


def test_ocr_layout_callback_none_when_provider_missing(monkeypatch):
    monkeypatch.setattr(ocr_mod, "ocr_provider_available", lambda: False)
    assert ocr_mod.ocr_layout_callback() is None


def test_extract_page_falls_back_to_native_on_tesseract_attribute_error():
    native = "Bon de commande fournisseur XYZ total ht 100,00"
    layout = {
        "source": "pdf_text",
        "width": 100,
        "height": 100,
        "lines": [{"text": native, "bbox": {"x0": 10, "y0": 10, "x1": 90, "y1": 20}}],
    }

    text, out_layout, source = extract_page_with_selective_ocr(
        native, layout, _blank_image(), _crash_ocr
    )
    assert text == native
    assert source == "pdf_text"
    assert out_layout["source"] == "pdf_text"


def test_extract_page_keeps_native_when_ocr_unavailable():
    native = "Bon de commande fournisseur XYZ total ht 100,00"
    layout = {
        "source": "pdf_text",
        "width": 100,
        "height": 100,
        "lines": [{"text": native, "bbox": {"x0": 10, "y0": 10, "x1": 90, "y1": 20}}],
    }

    def unavailable(_image):
        return {
            "text": "",
            "layout": {"source": "ocr_unavailable", "width": 80, "height": 80, "lines": []},
        }

    text, _out_layout, source = extract_page_with_selective_ocr(
        native, layout, _blank_image(), unavailable
    )
    assert "Bon de commande" in text
    assert source == "pdf_text"


def test_pdf_pages_keep_native_text_when_ocr_crashes():
    payload = _native_order_pdf()
    pages = pdf_pages_to_text(payload, "1", ocr_with_layout=_crash_ocr)
    assert pages
    text = pages[0]["text"]
    assert "167658" in text
    assert "15/02/2024" in text
    assert "7736504816" in text
    assert pages[0]["source"] == "pdf_text"


def test_is_ocr_runtime_error_detects_tesseract_attribute_error():
    import server

    exc = AttributeError("'NoneType' object has no attribute 'TesseractError'")
    assert server._is_ocr_runtime_error(exc) is True
    assert server._is_ocr_runtime_error(ValueError("PDF is password-protected")) is False


def test_local_process_does_not_map_ocr_crash_to_pdf_parse_failure(monkeypatch):
    import server

    payload = _native_order_pdf()
    monkeypatch.setattr(server, "_persist_uploaded_pdf", lambda *a, **k: None)
    monkeypatch.setattr("app.ocr.ocr_layout_callback", lambda: _crash_ocr)

    result = server._local_process_and_respond(
        payload, "1.2 PIECES XPRESS 167658.pdf", bypass_cache=True
    )
    assert (result.get("rejection") or {}).get("reason") != "PDF_PARSE_FAILURE"
    assert result.get("status") != "ERROR"


def test_local_process_uses_native_text_when_ocr_unavailable(monkeypatch):
    import server

    payload = _native_order_pdf()
    monkeypatch.setattr(server, "_persist_uploaded_pdf", lambda *a, **k: None)
    monkeypatch.setattr("app.ocr.ocr_layout_callback", lambda: None)

    result = server._local_process_and_respond(payload, "pieces-xpress.pdf", bypass_cache=True)
    assert (result.get("rejection") or {}).get("reason") != "PDF_PARSE_FAILURE"
    assert result.get("status") != "ERROR"
