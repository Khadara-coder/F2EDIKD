import sqlite3
from pathlib import Path

db = Path(__file__).resolve().parents[1] / "data" / "edifact_standalone.db"
c = sqlite3.connect(db)
c.row_factory = sqlite3.Row
for r in c.execute(
    "SELECT order_id, client_name, customer_order_number FROM file2edi_orders ORDER BY updated_at DESC LIMIT 5"
):
    print(dict(r))
    oid = r["order_id"]
    p = c.execute(
        "SELECT partner_id, partner_function, partner_code FROM file2edi_order_partners "
        "WHERE order_id=? AND partner_function='shipto'",
        [oid],
    ).fetchone()
    print(" shipto", dict(p) if p else None)
c.close()
