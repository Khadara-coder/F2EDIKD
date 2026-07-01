from __future__ import annotations

from typing import Any

from app.engine import FullCodeEngine, get_engine


def run_full_code_extraction(
    text: str,
    *,
    filename: str | None = None,
    layout: dict | None = None,
    instruction: str = "",
    extraction_context: dict | None = None,
) -> dict[str, Any]:
    from app.extraction import extract_candidate_fields

    return extract_candidate_fields(text, instruction, filename, layout, extraction_context or {})


def run_structured_extraction(
    text: str,
    *,
    filename: str | None = None,
    layout: dict | None = None,
    extraction_context: dict | None = None,
) -> dict[str, Any]:
    fields = run_full_code_extraction(
        text,
        filename=filename,
        layout=layout,
        instruction="",
        extraction_context=extraction_context,
    )
    return fields.get("structured", {})


__all__ = ["FullCodeEngine", "get_engine", "run_full_code_extraction", "run_structured_extraction"]
