from __future__ import annotations

import os
from io import BytesIO
from typing import Callable

import fitz
from PIL import Image

from app.config import get_config
from app.layout_geometry import bbox_from_values, union_bbox
from app.pdf_extract import extract_page_with_selective_ocr
from app.text_utils import compact_text


def render_pdf_page(page: fitz.Page) -> Image.Image:
    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    return Image.open(BytesIO(pixmap.tobytes("png"))).convert("RGB")


def pdf_page_layout(page: fitz.Page) -> dict:
    words = page.get_text("words") or []
    grouped: dict[tuple[int, int], list[tuple]] = {}
    for word in words:
        if len(word) < 8:
            continue
        text = compact_text(str(word[4]))
        if not text:
            continue
        key = (int(word[5]), int(word[6]))
        grouped.setdefault(key, []).append(word)

    lines = []
    for (_block_no, _line_no), line_words in grouped.items():
        line_words = sorted(line_words, key=lambda item: item[0])
        boxes = [bbox_from_values(item[0], item[1], item[2], item[3]) for item in line_words]
        lines.append(
            {
                "text": compact_text(" ".join(str(item[4]) for item in line_words)),
                "bbox": union_bbox(boxes),
            }
        )
    lines.sort(key=lambda line: (line["bbox"]["y0"], line["bbox"]["x0"]))
    return {
        "source": "pdf_text",
        "width": float(page.rect.width),
        "height": float(page.rect.height),
        "lines": lines,
    }


def parse_page_selection(selection: str, page_count: int, limit: int | None = None) -> list[int]:
    if limit is None:
        limit = int(get_config().get("pdf", {}).get("max_pages_per_request", 8))
    value = (selection or "1").replace(" ", "")
    pages: list[int] = []
    for part in value.split(","):
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start, end = int(start_text), int(end_text)
            pages.extend(range(start, end + 1))
        else:
            pages.append(int(part))

    if not pages:
        pages = [1]

    unique_pages: list[int] = []
    for page in pages:
        if page < 1 or page > page_count:
            raise ValueError(f"Page {page} is outside the PDF range 1-{page_count}.")
        if page not in unique_pages:
            unique_pages.append(page)

    if len(unique_pages) > limit:
        raise ValueError(f"Too many pages selected. Limit is {limit} pages per request.")
    return unique_pages


def pdf_pages_to_text(
    payload: bytes,
    selection: str = "1",
    *,
    ocr_with_layout: Callable[[Image.Image], dict] | None = None,
    limit: int | None = None,
) -> list[dict]:
    document = fitz.open(stream=payload, filetype="pdf")
    if document.page_count == 0:
        raise ValueError("The PDF has no pages.")

    pages: list[dict] = []
    for page_number in parse_page_selection(selection, document.page_count, limit=limit):
        page = document.load_page(page_number - 1)
        native_text = page.get_text("text") or ""
        layout = pdf_page_layout(page)
        source = "pdf_text" if compact_text(native_text) else "pdf_empty"
        text = native_text

        if ocr_with_layout is not None:
            page_image = render_pdf_page(page)
            text, layout, source = extract_page_with_selective_ocr(
                native_text,
                layout,
                page_image,
                ocr_with_layout,
                render_scale=2.0,
            )

        pages.append(
            {
                "page": page_number,
                "text": text,
                "layout": layout,
                "source": source,
            }
        )
    return pages
