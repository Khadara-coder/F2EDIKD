from __future__ import annotations

from typing import Any

from app.line_items import extract_line_items
from app.masterdata import get_master_data


class OrderLinesEngine:
    """Extract purchase order line items and enrich them with materials masterdata."""

    ENGINE_NAME = "order_lines"

    def extract(
        self,
        text: str,
        *,
        layout: dict | None = None,
        materials_by_id: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if materials_by_id is None:
            materials_by_id = get_master_data().get("materials_by_id", {})
        return {
            "engine": self.ENGINE_NAME,
            "lines": extract_line_items(text, layout, materials_by_id),
        }
