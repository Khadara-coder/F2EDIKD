from __future__ import annotations

import os

try:
    import pytesseract as _pytesseract_mod
    pytesseract = _pytesseract_mod
    _PYTESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None  # type: ignore[assignment]
    _PYTESSERACT_AVAILABLE = False
from PIL import Image, ImageOps

from app.layout_geometry import bbox_from_values, union_bbox
from app.text_utils import compact_text

TESSERACT_LANG = os.getenv("TESSERACT_LANG", "fra+eng")


def ocr_image_with_layout(image: Image.Image) -> dict:
    prepared = ImageOps.grayscale(image)
    try:
        data = pytesseract.image_to_data(prepared, lang=TESSERACT_LANG, output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractError:
        try:
            data = pytesseract.image_to_data(prepared, lang="eng", output_type=pytesseract.Output.DICT)
        except pytesseract.TesseractError:
            text = pytesseract.image_to_string(prepared, lang="eng")
            return {
                "text": text,
                "layout": {"source": "ocr", "width": image.width, "height": image.height, "lines": []},
            }

    grouped: dict[tuple[int, int, int], list[dict]] = {}
    for index, raw_text in enumerate(data.get("text", [])):
        text = compact_text(raw_text or "")
        if not text:
            continue
        try:
            confidence = float(data.get("conf", ["-1"])[index])
        except ValueError:
            confidence = -1
        if confidence < 0:
            continue
        left = int(data["left"][index])
        top = int(data["top"][index])
        width = int(data["width"][index])
        height = int(data["height"][index])
        key = (
            int(data.get("block_num", [0])[index]),
            int(data.get("par_num", [0])[index]),
            int(data.get("line_num", [0])[index]),
        )
        grouped.setdefault(key, []).append(
            {
                "text": text,
                "bbox": bbox_from_values(left, top, left + width, top + height),
            }
        )

    lines = []
    for words in grouped.values():
        words = sorted(words, key=lambda item: item["bbox"]["x0"])
        lines.append(
            {
                "text": compact_text(" ".join(word["text"] for word in words)),
                "bbox": union_bbox([word["bbox"] for word in words]),
            }
        )
    lines.sort(key=lambda line: (line["bbox"]["y0"], line["bbox"]["x0"]))
    text = "\n".join(line["text"] for line in lines)
    if not text:
        try:
            text = pytesseract.image_to_string(prepared, lang=TESSERACT_LANG)
        except pytesseract.TesseractError:
            text = pytesseract.image_to_string(prepared, lang="eng")

    return {
        "text": text,
        "layout": {"source": "ocr", "width": image.width, "height": image.height, "lines": lines},
    }


def ocr_image(image: Image.Image) -> str:
    return ocr_image_with_layout(image)["text"]


def ocr_provider_available() -> bool:
    """Return True only if pytesseract is installed AND tesseract binary is callable."""
    if not _PYTESSERACT_AVAILABLE or pytesseract is None:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False
