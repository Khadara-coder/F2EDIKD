from __future__ import annotations

from typing import Any

from app.engines.customer_order import CustomerOrderNumberEngine
from app.engines.delivery_address import DeliveryAddressEngine
from app.engines.order_lines import OrderLinesEngine
from app.engines.shipto_matching import ShipToMatchingEngine
from app.engines.tax_identification import TaxIdentificationEngine


class PurchaseOrderEngine:
    """Coordinate specialized engines for a purchase order document."""

    ENGINE_NAME = "purchase_order"

    def __init__(
        self,
        *,
        customer_order_engine: CustomerOrderNumberEngine | None = None,
        delivery_engine: DeliveryAddressEngine | None = None,
        shipto_engine: ShipToMatchingEngine | None = None,
        lines_engine: OrderLinesEngine | None = None,
        tax_engine: TaxIdentificationEngine | None = None,
    ) -> None:
        self.customer_order_engine = customer_order_engine or CustomerOrderNumberEngine()
        self.delivery_engine = delivery_engine or DeliveryAddressEngine()
        self.shipto_engine = shipto_engine or ShipToMatchingEngine()
        self.lines_engine = lines_engine or OrderLinesEngine()
        self.tax_engine = tax_engine or TaxIdentificationEngine()

    def run(
        self,
        *,
        text: str,
        fields: dict,
        filename: str | None = None,
        layout: dict | None = None,
        order_number: str | None = None,
        known_soldto_id: str | None = None,
    ) -> dict[str, Any]:
        tax = self.tax_engine.extract(text)
        customer_order = self.customer_order_engine.extract(text, filename)
        resolved_order_number = order_number or customer_order.get("order_number")
        enriched_fields = {
            **fields,
            "vat_numbers": tax.get("vat_numbers", []),
            "tax_identification": tax,
            "customer_order_number": customer_order,
        }
        delivery = self.delivery_engine.detect(text, filename=filename, layout=layout)
        shipto = self.shipto_engine.resolve_best(
            text=text,
            fields=enriched_fields,
            filename=filename,
            layout=layout,
            layout_analysis=delivery["layout_analysis"],
            order_number=resolved_order_number,
            known_soldto_id=known_soldto_id,
        )
        lines = self.lines_engine.extract(text, layout=layout)
        return {
            "engine": self.ENGINE_NAME,
            "customer_order_number": customer_order,
            "delivery": delivery,
            "tax_identification": tax,
            "shipto": shipto,
            "line_items": lines,
        }
