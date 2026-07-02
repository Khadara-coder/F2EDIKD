"""Simulate full shipto select flow."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.file2edi.store import get_store

store = get_store()
oid = "ord-rexel-026545008"
pid = "p-shipto-1"

payload = {
    "partnerCode": "15005248",
    "partnerName": ".REXEL",
    "addressLine1": "test street",
    "postalCode": "29490",
    "city": "GUIPAVAS",
    "country": "FR",
}

print("1. update_partner")
try:
    r = store.update_partner(pid, payload)
    print("   ok", r["partners"][1]["partnerCode"] if r else "fail")
except Exception as e:
    import traceback
    traceback.print_exc()

print("2. update_order_header clientName")
try:
    r2 = store.update_order_header(oid, {"clientName": ".REXEL"})
    print("   ok", r2["order"]["clientName"] if r2 else "fail")
except Exception as e:
    import traceback
    traceback.print_exc()
