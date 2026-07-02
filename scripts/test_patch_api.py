import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
import server

client = TestClient(server.app)
payload = {
    "partnerCode": "15005248",
    "partnerName": ".REXEL",
    "addressLine1": "RUE TEST",
    "postalCode": "29490",
    "city": "GUIPAVAS",
    "country": "FR",
}
r = client.patch("/api/orders/partners/p-shipto-1", json=payload)
print("status", r.status_code)
if r.status_code != 200:
    print(r.text[:500])
else:
    shipto = next(p for p in r.json()["partners"] if p["partnerFunction"] == "shipto")
    print("shipto", shipto["partnerCode"], shipto["partnerName"])
