from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.golden_compare import compare_structured, load_json
from tests.conftest import FIXTURES_DIR
from tests.golden_runner import extract_candidate_fields


def golden_cases() -> list[Path]:
    if not FIXTURES_DIR.exists():
        return []
    return sorted(path for path in FIXTURES_DIR.iterdir() if path.is_dir() and (path / "input.txt").exists())


@pytest.mark.parametrize("case_dir", golden_cases(), ids=lambda path: path.name)
def test_golden_extraction(case_dir: Path, master_data_ready):
    text = (case_dir / "input.txt").read_text(encoding="utf-8")
    meta = load_json(case_dir / "meta.json") if (case_dir / "meta.json").exists() else {}
    layout = load_json(case_dir / "layout.json") if (case_dir / "layout.json").exists() else None
    expected = load_json(case_dir / "expected.json")

    fields = extract_candidate_fields(
        text,
        meta.get("instruction", ""),
        meta.get("filename"),
        layout,
        {},
    )
    structured = fields.get("structured", {})
    errors = compare_structured(structured, expected)
    assert not errors, "\n".join(f"- {error}" for error in errors)
