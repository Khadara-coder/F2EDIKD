"""SAP processing feedback: match File2EDI sent orders against DB_Salesorder.

Only orders with status ``Envoyé SAP`` and a non-empty ``sap_sent_at`` are
eligible. Matching uses customer PO (BSTNK) and prefers sales orders created
on/after the send day so historical duplicates do not false-confirm.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

STATUS_SENT = "Envoyé SAP"
STATUS_CONFIRMED = "Confirmé SAP"


def normalize_po(value: str | None) -> str:
    raw = str(value or "").strip().split("/")[0].strip()
    return re.sub(r"\s+", "", raw.upper())


def normalize_kunnr(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.isdigit():
        return text.lstrip("0") or "0"
    return text.upper()


def parse_erdat(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 8:
        try:
            return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_sent_day(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).date()
    except ValueError:
        return parse_erdat(text)


def build_salesorder_index(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        bstnk = normalize_po(_row_get(row, "BSTNK", "bstnk"))
        vbeln = _row_get(row, "VBELN", "vbeln")
        if not bstnk or not vbeln:
            continue
        record = {
            "bstnk": bstnk,
            "vbeln": vbeln,
            "kunnr": normalize_kunnr(_row_get(row, "KUNNR", "kunnr")),
            "erdat": _row_get(row, "ERDAT", "erdat"),
            "erdat_date": parse_erdat(_row_get(row, "ERDAT", "erdat")),
        }
        index.setdefault(bstnk, []).append(record)
    return index


def find_sap_confirmation(
    *,
    customer_order_number: str | None,
    soldto: str | None,
    sap_sent_at: str | None,
    salesorders_by_bstnk: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    """Return the best Salesorder hit for a previously sent File2EDI order."""
    po = normalize_po(customer_order_number)
    if not po:
        return None
    candidates = list(salesorders_by_bstnk.get(po) or [])
    if not candidates:
        return None

    sent_day = parse_sent_day(sap_sent_at)
    soldto_norm = normalize_kunnr(soldto)

    eligible: list[dict[str, Any]] = []
    for candidate in candidates:
        erdat_date = candidate.get("erdat_date")
        if sent_day and erdat_date and erdat_date < sent_day:
            # Historical SO with same BSTNK - not feedback for this send.
            continue
        eligible.append(candidate)

    if not eligible:
        return None

    if soldto_norm:
        with_soldto = [c for c in eligible if c.get("kunnr") == soldto_norm]
        if with_soldto:
            eligible = with_soldto

    def _sort_key(item: dict[str, Any]) -> tuple:
        erdat_date = item.get("erdat_date") or date.max
        return (erdat_date, str(item.get("vbeln") or ""))

    best = sorted(eligible, key=_sort_key)[0]
    return {
        "vbeln": best.get("vbeln"),
        "bstnk": best.get("bstnk"),
        "kunnr": best.get("kunnr"),
        "erdat": best.get("erdat"),
    }


def reconcile_sent_orders_with_sap(store=None) -> dict[str, Any]:
    """Confirm only ``Envoyé SAP`` orders that appear in refreshed Salesorder data."""
    from src.file2edi.store import get_store
    from src.masterdata_runtime import table_records

    store = store or get_store()
    rows = table_records("salesorders")
    index = build_salesorder_index(rows)
    awaiting = store.list_orders_awaiting_sap_feedback()

    confirmed: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    skipped = 0

    for order in awaiting:
        status = str(order.get("status") or "").strip()
        sap_sent_at = str(order.get("sap_sent_at") or "").strip()
        # Hard guard: never confirm unless already sent to SAP.
        if status != STATUS_SENT or not sap_sent_at:
            skipped += 1
            continue

        hit = find_sap_confirmation(
            customer_order_number=order.get("customer_order_number"),
            soldto=order.get("soldto"),
            sap_sent_at=sap_sent_at,
            salesorders_by_bstnk=index,
        )
        order_id = str(order.get("order_id") or "")
        if not hit or not hit.get("vbeln"):
            unmatched.append({
                "orderId": order_id,
                "customerOrderNumber": order.get("customer_order_number"),
            })
            continue

        ok = store.mark_sap_confirmed(
            order_id,
            vbeln=str(hit["vbeln"]),
            erdat=str(hit.get("erdat") or "") or None,
        )
        if ok:
            confirmed.append({
                "orderId": order_id,
                "customerOrderNumber": order.get("customer_order_number"),
                "vbeln": hit["vbeln"],
                "erdat": hit.get("erdat"),
            })
        else:
            skipped += 1

    result = {
        "ok": True,
        "salesorderRows": len(rows),
        "awaiting": len(awaiting),
        "confirmed": len(confirmed),
        "unmatched": len(unmatched),
        "skipped": skipped,
        "confirmedOrders": confirmed,
        "unmatchedOrders": unmatched[:50],
    }
    log.info(
        "SAP feedback reconcile: awaiting=%s confirmed=%s unmatched=%s skipped=%s",
        result["awaiting"],
        result["confirmed"],
        result["unmatched"],
        result["skipped"],
    )
    return result


def enrich_all_orders_vbeln(store=None) -> int:
    """Backfill sap_vbeln for all orders missing it, using salesorders masterdata."""
    from src.file2edi.store import get_store
    from src.masterdata_runtime import table_records

    store = store or get_store()
    rows = table_records("salesorders")
    if not rows:
        return 0
    index = build_salesorder_index(rows)

    conn = store._conn()
    orders = conn.execute(
        """SELECT order_id, customer_order_number, soldto, sap_sent_at
           FROM file2edi_orders
           WHERE (sap_vbeln IS NULL OR sap_vbeln = '')
             AND customer_order_number IS NOT NULL
             AND customer_order_number != ''"""
    ).fetchall()

    updated = 0
    for order in orders:
        hit = find_sap_confirmation(
            customer_order_number=order["customer_order_number"],
            soldto=order["soldto"],
            sap_sent_at=order["sap_sent_at"],
            salesorders_by_bstnk=index,
        )
        if hit and hit.get("vbeln"):
            conn.execute(
                "UPDATE file2edi_orders SET sap_vbeln=? WHERE order_id=?",
                (str(hit["vbeln"]), str(order["order_id"])),
            )
            updated += 1
    if updated:
        conn.commit()
    conn.close()
    log.info("VBELN enrichment: %s orders updated out of %s candidates", updated, len(orders))
    return updated


def _row_get(row: dict[str, Any], *names: str) -> str:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        value = lowered.get(str(name).strip().lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""
