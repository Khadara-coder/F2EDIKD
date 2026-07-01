from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _get_path(data: dict[str, Any], dotted_path: str) -> Any:
    current: Any = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def compare_structured(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    for key, value in expected.items():
        if key.endswith("_min_count"):
            list_path = key[: -len("_min_count")]
            items = _get_path(actual, list_path)
            if not isinstance(items, list) or len(items) < int(value):
                errors.append(f"{list_path}: expected at least {value} items, got {len(items) if isinstance(items, list) else 0}")
            continue

        if isinstance(value, dict):
            actual_value = _get_path(actual, key) if "." in key else actual.get(key)
            if not isinstance(actual_value, dict):
                errors.append(f"{key}: expected object, got {type(actual_value).__name__}")
                continue
            for sub_key, sub_value in value.items():
                if actual_value.get(sub_key) != sub_value:
                    errors.append(f"{key}.{sub_key}: expected {sub_value!r}, got {actual_value.get(sub_key)!r}")
            continue

        actual_value = _get_path(actual, key) if "." in key else actual.get(key)
        if actual_value != value:
            errors.append(f"{key}: expected {value!r}, got {actual_value!r}")

    return errors


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
