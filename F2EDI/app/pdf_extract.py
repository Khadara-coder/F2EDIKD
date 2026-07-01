from __future__ import annotations

from typing import Callable

from PIL import Image

from app.ocr_regions import (
    merge_page_layouts,
    merge_page_text,
    needs_selective_ocr,
    selective_crop_box,
)
from app.text_utils import compact_text


def extract_page_with_selective_ocr(
    native_text: str,
    native_layout: dict,
    page_image: Image.Image,
    ocr_with_layout: Callable[[Image.Image], dict],
    render_scale: float = 2.0,
) -> tuple[str, dict, str]:
    if not needs_selective_ocr(native_text, native_layout):
        return native_text, native_layout, "pdf_text"

    crop_box = selective_crop_box(page_image.width, page_image.height, native_layout)
    cropped = page_image.crop(crop_box)
    ocr_result = ocr_with_layout(cropped)
    merged_text = merge_page_text(native_text, ocr_result.get("text", ""))
    merged_layout = merge_page_layouts(
        native_layout,
        ocr_result.get("layout") or {},
        crop_box,
        render_scale,
    )
    source = "ocr_crop" if not compact_text(native_text) else "pdf_text+ocr_crop"
    return merged_text, merged_layout, source
