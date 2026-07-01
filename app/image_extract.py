from __future__ import annotations

from typing import Callable

from PIL import Image

from app.config import get_config
from app.ocr_regions import merge_page_layouts, selective_crop_box


def extract_image_with_selective_ocr(
    image: Image.Image,
    ocr_with_layout: Callable[[Image.Image], dict],
) -> tuple[str, dict, str]:
    cfg = get_config().get("ocr", {})
    if not cfg.get("selective_crop_enabled", True):
        result = ocr_with_layout(image)
        layout = result.get("layout") or {"source": "ocr", "width": image.width, "height": image.height, "lines": []}
        return result.get("text", ""), layout, "ocr"

    crop_box = selective_crop_box(image.width, image.height, None)
    full_page = crop_box == (0, 0, image.width, image.height)
    if full_page or image.height < 500:
        result = ocr_with_layout(image)
        layout = result.get("layout") or {"source": "ocr", "width": image.width, "height": image.height, "lines": []}
        return result.get("text", ""), layout, "ocr"

    crop_result = ocr_with_layout(image.crop(crop_box))
    base_layout = {"source": "image", "width": float(image.width), "height": float(image.height), "lines": []}
    merged_layout = merge_page_layouts(base_layout, crop_result.get("layout") or {}, crop_box, 1.0)
    return crop_result.get("text", ""), merged_layout, "ocr_crop"
