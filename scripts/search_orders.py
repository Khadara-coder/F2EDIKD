import sqlite3
from pathlib import Path

db = Path(__file__).resolve().parents[1] / "data" / "edifact_standalone.db"
c = sqlite3.connect(db)
c.row_factory = sqlite3.Row
rows = c.execute(
    "SELECT order_id, customer_order_number, client_name, order_date, line_count "
    "FROM file2edi_orders WHERE customer_order_number LIKE '%CAC%' OR client_name LIKE '%ISERBA%'"
).fetchall()
print("ISERBA/CAC orders:", [dict(r) for r in rows])
rows2 = c.execute(
    "SELECT order_id, partner_function, partner_code, partner_name "
    "FROM file2edi_order_partners WHERE partner_code LIKE '%15018063%'"
).fetchall()
print("shipto 15018063:", [dict(r) for r in rows2])
rows3 = c.execute(
    "SELECT order_id, COUNT(*) n FROM file2edi_order_lines GROUP BY order_id"
).fetchall()
print("lines per order:", [dict(r) for r in rows3])
c.close()
