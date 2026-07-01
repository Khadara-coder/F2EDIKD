from __future__ import annotations

from app.config import get_config
from app.text_utils import compact_text, fold_text


def _anchor_keywords() -> list[str]:
    return get_config().get("anchors", {}).get("delivery", [])


def needs_selective_ocr(text: str, layout: dict | None) -> bool:
    cfg = get_config().get("ocr", {})
    if not cfg.get("selective_crop_enabled", True):
        min_native_chars = int(cfg.get("min_native_text_chars", 30))
        return len(compact_text(text)) < min_native_chars

    min_native_chars = int(cfg.get("min_native_text_chars", 30))
    compact = compact_text(text)
    if len(compact) < min_native_chars:
        return True

    folded = fold_text(compact)
    keywords = _anchor_keywords()
    has_anchor = any(keyword in folded for keyword in keywords)
    has_postal = any(ch.isdigit() for ch in compact) and any(
        token.isdigit() and len(token) == 5 for token in compact.split()
    )
    if not has_anchor and not has_postal:
        return True

    if layout and layout.get("lines"):
        line_texts = fold_text("\n".join(line.get("text", "") for line in layout["lines"]))
        if keywords and not any(keyword in line_texts for keyword in keywords):
            return True
    return False


def selective_crop_box(image_width: int, image_height: int, layout: dict | None = None) -> tuple[int, int, int, int]:
    cfg = get_config().get("ocr", {})
    top_ratio = float(cfg.get("selective_crop_top_ratio", 0.55))
    margin_px = int(cfg.get("selective_crop_margin_px", 12))

    if layout and layout.get("lines"):
        anchor_lines = []
        for line in layout["lines"]:
            folded = fold_text(line.get("text", ""))
            if any(keyword in folded for keyword in _anchor_keywords()):
                anchor_lines.append(line)
        if anchor_lines:
            x0 = min(line["bbox"]["x0"] for line in anchor_lines)
            y0 = min(line["bbox"]["y0"] for line in anchor_lines)
            x1 = max(line["bbox"]["x1"] for line in anchor_lines)
            y1 = max(line["bbox"]["y1"] for line in anchor_lines)
            scale_x = image_width / max(float(layout.get("width") or image_width), 1.0)
            scale_y = image_height / max(float(layout.get("height") or image_height), 1.0)
            left = max(0, int(x0 * scale_x) - margin_px)
            top = max(0, int(y0 * scale_y) - margin_px)
            right = min(image_width, int(max(x1, x0 + image_width * 0.45) * scale_x) + margin_px)
            bottom = min(image_height, int(y1 * scale_y + image_height * 0.22) + margin_px)
            if right - left >= 80 and bottom - top >= 80:
                return left, top, right, bottom

    bottom = max(int(image_height * top_ratio), 120)
    return 0, 0, image_width, min(image_height, bottom)


def merge_page_layouts(
    base_layout: dict,
    crop_layout: dict,
    crop_box: tuple[int, int, int, int],
    render_scale: float,
) -> dict:
    left, top, _right, _bottom = crop_box
    merged_lines = list(base_layout.get("lines", []))
    seen = {compact_text(line.get("text", "")).lower() for line in merged_lines if line.get("text")}

    for line in crop_layout.get("lines", []):
        text = compact_text(line.get("text", ""))
        if not text or text.lower() in seen:
            continue
        bbox = line.get("bbox") or {}
        merged_lines.append(
            {
                "text": text,
                "bbox": {
                    "x0": (float(bbox.get("x0", 0)) + left) / render_scale,
                    "y0": (float(bbox.get("y0", 0)) + top) / render_scale,
                    "x1": (float(bbox.get("x1", 0)) + left) / render_scale,
                    "y1": (float(bbox.get("y1", 0)) + top) / render_scale,
                },
            }
        )
        seen.add(text.lower())

    merged_lines.sort(key=lambda line: (line["bbox"]["y0"], line["bbox"]["x0"]))
    return {
        "source": "pdf_text+ocr_crop",
        "width": float(base_layout.get("width") or crop_layout.get("width") or 1),
        "height": float(base_layout.get("height") or crop_layout.get("height") or 1),
        "lines": merged_lines,
    }


def merge_page_text(base_text: str, crop_text: str) -> str:
    base_lines = [line.strip() for line in base_text.splitlines() if line.strip()]
    extra_lines = [line.strip() for line in crop_text.splitlines() if line.strip()]
    if not extra_lines:
        return "\n".join(base_lines)
    if not base_lines:
        return "\n".join(extra_lines)

    seen = {fold_text(line) for line in base_lines}
    merged = list(base_lines)
    for line in extra_lines:
        key = fold_text(line)
        if key not in seen:
            merged.append(line)
            seen.add(key)
    return "\n".join(merged)
