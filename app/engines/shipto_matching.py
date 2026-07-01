from __future__ import annotations

from typing import Any

from app.masterdata import resolve_delivery_with_masterdata, validate_delivery_with_master


class ShipToMatchingEngine:
    """Match a detected delivery address to the best masterdata SHIPTO."""

    ENGINE_NAME = "shipto_matching"

    def match(
        self,
        *,
        text: str,
        fields: dict,
        delivery_address: dict,
        filename: str | None = None,
        layout_analysis: dict | None = None,
        order_number: str | None = None,
        known_soldto_id: str | None = None,
    ) -> dict[str, Any]:
        result = validate_delivery_with_master(
            text,
            fields,
            filename,
            delivery_address,
            layout_analysis,
            order_number=order_number,
            known_soldto_id=known_soldto_id,
        )
        return {"engine": self.ENGINE_NAME, "shipto": result}

    def resolve_best(
        self,
        *,
        text: str,
        fields: dict,
        filename: str | None = None,
        layout: dict | None = None,
        layout_analysis: dict | None = None,
        order_number: str | None = None,
        known_soldto_id: str | None = None,
    ) -> dict[str, Any]:
        detected, validated = resolve_delivery_with_masterdata(
            text,
            fields,
            filename,
            layout,
            layout_analysis,
            order_number=order_number,
            known_soldto_id=known_soldto_id,
        )
        return {
            "engine": self.ENGINE_NAME,
            "detected_address": detected,
            "shipto": validated,
        }
