"""Diagnose EDIFACT generation blockers for recent orders."""
import asyncio
import json
import sqlite3
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.file2edi.store import File2EdiStore
from src.file2edi.router import _corrections_from_review, _ensure_conversion_for_generate, _extract_generate_errors
import server as srv

DB = Path(__file__).resolve().parents[1] / "data" / "edifact_standalone.db"
store = File2EdiStore(str(DB), str(Path(__file__).resolve().parents[1] / "data" / "intake"))

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
orders = conn.execute(
    "SELECT order_id FROM file2edi_orders ORDER BY updated_at DESC LIMIT 5"
).fetchall()
conn.close()

srv._load_masterdata_cache()


async def diag(order_id: str) -> None:
    review = store.load_order_review(order_id)
    if not review:
        print(f"{order_id}: NO REVIEW")
        return
    o = review["order"]
    soldto = next((p for p in review["partners"] if p["partnerFunction"] == "soldto"), {})
    shipto = next((p for p in review["partners"] if p["partnerFunction"] == "shipto"), {})
    print(f"\n=== {order_id[:28]} ===")
    print(f"  po={o.get('customerOrderNumber')!r} date={o.get('orderDate')!r}")
    print(f"  soldto={soldto.get('partnerCode')!r} shipto={shipto.get('partnerCode')!r}")
    print(f"  lines={len(review.get('lines', []))}")
    for ln in review.get("lines", []):
        print(f"    L{ln.get('lineNumber')}: art={ln.get('boschArticle')!r} qty={ln.get('quantity')}")

    _ensure_conversion_for_generate(order_id, review)
    cor = _corrections_from_review(review)

    class FakeReq:
        async def json(self):
            return {"corrections": cor}

    r = await srv.api_generate(order_id, FakeReq())
    if hasattr(r, "status_code"):
        print(f"  RESULT: HTTP {r.status_code}")
        return
    if r.get("generated"):
        print(f"  RESULT: OK {r.get('tst_filename')}")
    else:
        print(f"  RESULT: BLOCKED")
        for e in _extract_generate_errors(r):
            print(f"    - {e}")


async def main():
    for row in orders:
        await diag(row["order_id"])


if __name__ == "__main__":
    asyncio.run(main())
