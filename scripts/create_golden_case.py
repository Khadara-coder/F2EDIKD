#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for name in ("torch", "transformers", "accelerate", "decord"):
    if name not in sys.modules:
        try:
            __import__(name)
        except ImportError:
            sys.modules[name] = MagicMock()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or refresh a golden extraction fixture.")
    parser.add_argument("--name", required=True, help="Case folder name, e.g. 04_my_pdf")
    parser.add_argument("--text", help="Path to a text file to use as extracted input")
    parser.add_argument("--pdf", help="Path to a PDF file")
    parser.add_argument("--pages", default="1", help="PDF pages selection, e.g. 1 or 1-2")
    parser.add_argument("--filename", help="Original filename metadata")
    parser.add_argument("--instruction", default="Extraire commande, client et adresse de livraison")
    parser.add_argument("--write-expected", action="store_true", help="Also write expected.json from current extractor output")
    args = parser.parse_args()

    case_dir = ROOT / "tests" / "fixtures" / "golden" / args.name
    case_dir.mkdir(parents=True, exist_ok=True)

    layout = None
    source_name = args.filename or ""

    if args.pdf:
        import fitz

        from app.server import extract_page_with_selective_ocr, ocr_image_with_layout, pdf_page_layout, render_pdf_page
        from app.server import parse_page_selection

        pdf_path = Path(args.pdf)
        source_name = source_name or pdf_path.name
        document = fitz.open(pdf_path)
        page_number = parse_page_selection(args.pages, document.page_count)[0]
        page = document.load_page(page_number - 1)
        native_text = page.get_text("text") or ""
        native_layout = pdf_page_layout(page)
        page_image = render_pdf_page(page)
        text, layout, _source = extract_page_with_selective_ocr(
            native_text,
            native_layout,
            page_image,
            ocr_image_with_layout,
            render_scale=2.0,
        )
        (case_dir / "layout.json").write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
    elif args.text:
        text = Path(args.text).read_text(encoding="utf-8")
        source_name = source_name or Path(args.text).name
    else:
        parser.error("Provide --text or --pdf")

    (case_dir / "input.txt").write_text(text, encoding="utf-8")
    (case_dir / "meta.json").write_text(
        json.dumps({"filename": source_name, "instruction": args.instruction}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if args.write_expected:
        from app.extraction import extract_candidate_fields

        fields = extract_candidate_fields(text, args.instruction, source_name, layout, {})
        structured = fields.get("structured", {})
        (case_dir / "expected.json").write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote full expected.json — trim it to the key fields you want to lock.")
    elif not (case_dir / "expected.json").exists():
        (case_dir / "expected.json").write_text("{}\n", encoding="utf-8")
        print("Created empty expected.json — add assertions manually.")

    print(f"Golden case ready: {case_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
