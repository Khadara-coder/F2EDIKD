from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for name in ("torch", "transformers", "accelerate", "decord"):
    if name not in sys.modules:
        try:
            __import__(name)
        except ImportError:
            sys.modules[name] = MagicMock()

from app.delivery import (
    analyze_delivery_layout,
    extract_delivery_address,
    resolve_delivery_address,
)
from app.extraction import extract_candidate_fields
from app.server import pdf_page_layout, pdf_pages_to_text


def main() -> None:
    pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "psp571536_1qcqzay7025 (6).pdf"
    payload = pdf_path.read_bytes()
    document = fitz.open(stream=payload, filetype="pdf")
    print(f"file: {pdf_path.name}")
    print(f"pages: {document.page_count}")

    page = document.load_page(0)
    native = page.get_text("text")
    layout = pdf_page_layout(page)
    print(f"layout lines: {len(layout.get('lines', []))}")
    print("--- native text ---")
    print(native[:4000])

    print("--- relevant layout lines ---")
    import re

    for line in layout.get("lines", []):
        text = line.get("text", "")
        lowered = text.lower()
        if (
            any(k in lowered for k in ["livraison", "facture", "ship", "bill", "commande", "client"])
            or re.search(r"\b\d{5}\b", text)
            or any(k in lowered for k in [" rue ", " avenue ", " route ", " boulevard ", " zac "])
        ):
            bbox = line["bbox"]
            print(f"  [{bbox['x0']:.0f},{bbox['y0']:.0f}] {text}")

    print("--- lines near delivery block ---")
    for line in layout.get("lines", []):
        text = line.get("text", "")
        if any(
            token in text.upper()
            for token in ["50180", "AGNEAUX", "LIVRAISON", "70478", "PERIERS", "DRANCY", "93700"]
        ):
            bbox = line["bbox"]
            print(f"  [{bbox['x0']:.0f},{bbox['y0']:.0f}-{bbox['y1']:.0f}] {text!r}")

    from app.delivery import build_layout_address_candidates

    print("--- raw layout address candidates (filtered postals) ---")
    for candidate in build_layout_address_candidates(layout):
        if candidate.get("Code postal") in {"50180", "70478", "93700", "50009", "36109"}:
            print(json.dumps(candidate, ensure_ascii=False))

    pages = pdf_pages_to_text(payload, "1")
    text = pages[0]["text"]
    layout2 = pages[0].get("layout") or layout
    print(f"pipeline source: {pages[0]['source']}")
    print(f"pipeline text length: {len(text)}")

    print("--- text delivery extract ---")
    print(json.dumps(extract_delivery_address(text, pdf_path.name), ensure_ascii=False, indent=2))

    layout_analysis = analyze_delivery_layout(layout2)
    print("--- layout candidates ---")
    for candidate in layout_analysis.get("address_candidates", [])[:8]:
        print(
            json.dumps(
                {
                    key: candidate.get(key)
                    for key in [
                        "Code postal",
                        "Ville",
                        "Rue",
                        "Nom / service",
                        "Score geometrie",
                        "Plus proche livraison que facturation",
                        "Distance livraison px",
                        "Distance facturation px",
                        "Distance livraison norm",
                        "Ancre positive",
                        "Ancre negative",
                        "Raisons geometrie",
                    ]
                },
                ensure_ascii=False,
            )
        )

    print("--- resolve ---")
    print(json.dumps(resolve_delivery_address(text, pdf_path.name, layout2, layout_analysis), ensure_ascii=False, indent=2))

    fields = extract_candidate_fields(text, "Extraire adresse livraison", pdf_path.name, layout2, {})
    structured = fields["structured"]
    validated = structured["adresses"]["Adresse de livraison validee"]
    print("--- masterdata validation ---")
    print(
        json.dumps(
            {
                key: validated.get(key)
                for key in [
                    "Statut",
                    "Confiance",
                    "Raison",
                    "SOLDTO",
                    "SHIPTO",
                    "Nom",
                    "Rue",
                    "Code postal",
                    "Ville",
                    "Buyer reason",
                    "Candidats geometrie",
                    "Ancres geometrie",
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print("order:", structured["document"].get("Numero de commande"))
    print("order masterdata:", structured["document"].get("Commande masterdata"))
    print("cross validation:", structured.get("validation"))


if __name__ == "__main__":
    main()
