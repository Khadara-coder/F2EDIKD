import sqlite3, json
from pathlib import Path

db = Path(__file__).resolve().parents[1] / "data" / "edifact_standalone.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
oid = "7b793ed0c4689a0f7e11801fd3538fd24c3b0dfb661f47ec4e7c0434a9220584"
row = conn.execute("SELECT * FROM file2edi_orders WHERE order_id=?", [oid]).fetchone()
if row:
    d = dict(row)
    ext = d.get("extraction_json")
    if ext:
        try:
            e = json.loads(ext)
            print("extraction order:", e.get("order"))
            print("extraction customer soldto/shipto:", e.get("customer", {}).get("soldto"), e.get("customer", {}).get("shipto"))
            lines = e.get("lines", {})
            print("extraction lines count:", lines.get("count"), "items:", len(lines.get("items") or []))
        except Exception as ex:
            print("ext parse err", ex)
    print("DB order:", {k: d[k] for k in d if k != "extraction_json"})
parts = conn.execute("SELECT * FROM file2edi_order_partners WHERE order_id=?", [oid]).fetchall()
print("partners:", len(parts))
for p in parts:
    print(dict(p))
lines = conn.execute("SELECT * FROM file2edi_order_lines WHERE order_id=?", [oid]).fetchall()
print("lines:", len(lines))
conn.close()
