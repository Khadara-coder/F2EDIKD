from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from app.extraction import build_text_extraction_result, update_extraction_context_from_structured
from app.image_extract import extract_image_with_selective_ocr
from app.ocr import ocr_image_with_layout, ocr_provider_available
from app.pdf_reader import pdf_pages_to_text
from app.runtime import configure_runtime, runtime_info


class FullCodeEngine:
    ENGINE_NAME = "full_code"

    def __init__(self, *, ocr_enabled: bool | None = None) -> None:
        configure_runtime()
        if ocr_enabled is None:
            ocr_enabled = ocr_provider_available()
        self._ocr_enabled = ocr_enabled

    @property
    def ocr_enabled(self) -> bool:
        return self._ocr_enabled

    def _ocr_with_layout(self) -> Callable | None:
        if not self._ocr_enabled:
            return None
        return ocr_image_with_layout

    def extract_pdf(
        self,
        payload: bytes,
        *,
        filename: str | None = None,
        pages: str = "1",
        instruction: str = "Extraire bon de commande B2B",
        include_debug: bool = False,
        extraction_context: dict | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        context = extraction_context if extraction_context is not None else {}
        text_pages = pdf_pages_to_text(payload, pages, ocr_with_layout=self._ocr_with_layout())
        results = []
        for item in text_pages:
            result = build_text_extraction_result(
                item["page"],
                item["text"],
                item["source"],
                instruction,
                filename,
                item.get("layout"),
                self.ENGINE_NAME,
                context,
                include_debug,
            )
            update_extraction_context_from_structured(context, result["fields"]["structured"])
            results.append(result)

        response: dict[str, Any] = {
            "filename": filename,
            "file_type": "pdf",
            "engine": self.ENGINE_NAME,
            "instruction": instruction,
            "pages": [item["page"] for item in results],
            "results": results,
            "extraction_context": {
                "order_number": context.get("order_number"),
                "known_soldto_id": context.get("known_soldto_id"),
            },
            "timings_ms": {"request_total": int((time.perf_counter() - started) * 1000)},
        }
        if include_debug and results:
            response["debug"] = results[-1].get("debug")
        return response

    def extract_image(
        self,
        image,
        *,
        filename: str | None = None,
        instruction: str = "Extraire bon de commande B2B",
        include_debug: bool = False,
        extraction_context: dict | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        context = extraction_context if extraction_context is not None else {}
        ocr = self._ocr_with_layout()
        if ocr is None:
            raise RuntimeError("OCR is not available on this runtime.")
        text, layout, source = extract_image_with_selective_ocr(image, ocr)
        result = build_text_extraction_result(
            1,
            text,
            source,
            instruction,
            filename,
            layout,
            self.ENGINE_NAME,
            context,
            include_debug,
        )
        update_extraction_context_from_structured(context, result["fields"]["structured"])
        response = {
            "filename": filename,
            "file_type": "image",
            "engine": self.ENGINE_NAME,
            "instruction": instruction,
            "pages": [1],
            "results": [result],
            "extraction_context": context,
            "timings_ms": {"request_total": int((time.perf_counter() - started) * 1000)},
        }
        if include_debug:
            response["debug"] = result.get("debug")
        return response

    def extract_file(
        self,
        payload: bytes,
        *,
        filename: str | None = None,
        pages: str = "1",
        instruction: str = "Extraire bon de commande B2B",
        include_debug: bool = False,
        extraction_context: dict | None = None,
    ) -> dict[str, Any]:
        suffix = Path(filename or "").suffix.lower()
        if suffix == ".pdf":
            return self.extract_pdf(
                payload,
                filename=filename,
                pages=pages,
                instruction=instruction,
                include_debug=include_debug,
                extraction_context=extraction_context,
            )
        if suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
            from PIL import Image
            from io import BytesIO

            image = Image.open(BytesIO(payload)).convert("RGB")
            return self.extract_image(
                image,
                filename=filename,
                instruction=instruction,
                include_debug=include_debug,
                extraction_context=extraction_context,
            )
        raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")

    def health(self) -> dict[str, Any]:
        from app.address_similarity import (
            availability_reason,
            embeddings_enabled,
            is_available,
            model_backend,
            model_dir,
        )
        from app.masterdata import get_master_data
        from app.postal_reference import load_postal_reference

        master_data = get_master_data()
        postal_reference = load_postal_reference()
        return {
            "engine": self.ENGINE_NAME,
            "ocr_enabled": self._ocr_enabled,
            "ocr_available": ocr_provider_available(),
            **runtime_info(),
            "master_data_loaded": master_data.get("loaded", False),
            "master_customers": len(master_data.get("customers", [])),
            "master_soldtos_with_shipto": len(master_data.get("partners_by_soldto", {})),
            "master_error": master_data.get("error", ""),
            "postal_reference_loaded": postal_reference.get("loaded", False),
            "postal_reference_path": postal_reference.get("path", ""),
            "postal_reference_communes": postal_reference.get("communes_count", 0),
            "postal_reference_postals": postal_reference.get("postal_count", 0),
            "postal_reference_error": postal_reference.get("error", ""),
            "embeddings_available": is_available(),
            "embeddings_enabled": embeddings_enabled(),
            "embeddings_model_dir": str(model_dir()),
            "embeddings_backend": model_backend(),
            "embeddings_error": availability_reason() if not is_available() else "",
        }


def get_engine(*, ocr_enabled: bool | None = None) -> FullCodeEngine:
    return FullCodeEngine(ocr_enabled=ocr_enabled)
