from __future__ import annotations

from typing import Any

from app.delivery import (
    analyze_delivery_layout,
    collect_delivery_address_candidates,
    resolve_delivery_address,
)


class DeliveryAddressEngine:
    """Detect the delivery address from document text and optional layout coordinates."""

    ENGINE_NAME = "delivery_address"

    def analyze_layout(self, layout: dict | None = None) -> dict[str, Any]:
        return analyze_delivery_layout(layout)

    def detect(
        self,
        text: str,
        *,
        filename: str | None = None,
        layout: dict | None = None,
        layout_analysis: dict | None = None,
    ) -> dict[str, Any]:
        if layout_analysis is None:
            layout_analysis = self.analyze_layout(layout)

        address = resolve_delivery_address(text, filename, layout, layout_analysis)
        candidates = collect_delivery_address_candidates(text, filename, layout, layout_analysis)
        return {
            "engine": self.ENGINE_NAME,
            "address": address,
            "candidates": candidates,
            "layout_analysis": layout_analysis,
        }
