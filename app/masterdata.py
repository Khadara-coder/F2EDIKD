from __future__ import annotations

import csv
import os
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from app.config import scoring_config
from app.text_utils import (
    extract_postal_codes,
    fold_text,
    norm_key,
    norm_name,
    norm_order_key,
    norm_postal,
    norm_vat,
    significant_tokens,
)

MASTER_DATA_DIR = Path(os.getenv("MASTER_DATA_DIR", "/data/masterdata"))

master_data_cache: dict[str, Any] | None = None
master_data_cache_fingerprint: tuple | None = None


def _normalize_for_index(s: str) -> str:
    """Normalize text for indexing: uppercase, no accents, no special chars."""
    import unicodedata as _ud
    if not s:
        return ""
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u2013", "-").replace("\u2014", "-").replace("\xa0", " ")
    s = "".join(c for c in _ud.normalize("NFD", s) if _ud.category(c) != "Mn")
    s = s.upper()
    import re as _re
    s = _re.sub(r"[^A-Z0-9\s]", " ", s)
    s = _re.sub(r"\s+", " ", s).strip()
    return s


def open_master_csv(path: Path):
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            handle = path.open("r", encoding=encoding, newline="")
            handle.read(1024)
            handle.seek(0)
            return handle
        except UnicodeDecodeError:
            continue
    return path.open("r", encoding="latin-1", errors="replace", newline="")


def current_master_data_fingerprint() -> tuple:
    names = ("10564_Customers.csv", "10564_Partners.csv", "10564_Materials.csv", "DB_Salesorder.csv")
    fingerprint = []
    for name in names:
        path = MASTER_DATA_DIR / name
        try:
            stat = path.stat()
            fingerprint.append((name, stat.st_size, stat.st_mtime_ns))
        except FileNotFoundError:
            fingerprint.append((name, None, None))
    return tuple(fingerprint)


def party_from_row(row: dict, id_column: str) -> dict:
    return {
        "id": (row.get(id_column) or "").strip(),
        "name": (row.get("NAME") or "").strip(),
        "street": (row.get("STRAS") or "").strip(),
        "city": (row.get("ORT01") or "").strip(),
        "postal": norm_postal(row.get("PSTLZ") or ""),
        "country": (row.get("LAND1") or "FR").strip(),
        "vat": norm_vat(row.get("VAT_NR") or ""),
    }


def address_text(party: dict) -> str:
    from app.text_utils import compact_text

    lines = [
        party.get("name", ""),
        party.get("street", ""),
        compact_text(f"{party.get('postal', '')} {party.get('city', '')}"),
        party.get("country", "FR"),
    ]
    return "\n".join(line for line in lines if line)


def get_master_data() -> dict[str, Any]:
    global master_data_cache, master_data_cache_fingerprint
    fingerprint = current_master_data_fingerprint()
    if master_data_cache is not None and master_data_cache_fingerprint == fingerprint:
        return master_data_cache

    customers_path = MASTER_DATA_DIR / "10564_Customers.csv"
    partners_path = MASTER_DATA_DIR / "10564_Partners.csv"
    materials_path = MASTER_DATA_DIR / "10564_Materials.csv"
    salesorders_path = MASTER_DATA_DIR / "DB_Salesorder.csv"
    data: dict[str, Any] = {
        "loaded": False,
        "error": "",
        "customers": [],
        "customers_by_id": {},
        "customers_by_vat": {},
        "customers_by_postal": {},
        "partners_by_soldto": {},
        "partners_by_postal": {},
        "partners_by_agency": {},
        "partners_by_normalized_city": {},
        "partners_by_normalized_street": {},
        "materials_by_id": {},
        "salesorders_by_bstnk": {},
        "salesorders_by_kunnr": {},
        "materials_count": 0,
        "salesorders_count": 0,
        "files": {},
    }
    if not customers_path.exists() or not partners_path.exists():
        data["error"] = f"Master data missing in {MASTER_DATA_DIR}"
        master_data_cache = data
        master_data_cache_fingerprint = fingerprint
        return data

    with open_master_csv(customers_path) as handle:
        reader = csv.DictReader(handle, delimiter=";")
        data["files"][customers_path.name] = {"columns": reader.fieldnames or [], "rows": 0}
        for row in reader:
            data["files"][customers_path.name]["rows"] += 1
            party = party_from_row(row, "SOLDTO")
            if not party["id"]:
                continue
            data["customers"].append(party)
            data["customers_by_id"][party["id"]] = party
            if party["vat"]:
                data["customers_by_vat"].setdefault(party["vat"], []).append(party)
            if party["postal"]:
                data["customers_by_postal"].setdefault(party["postal"], []).append(party)

    with open_master_csv(partners_path) as handle:
        reader = csv.DictReader(handle, delimiter=";")
        data["files"][partners_path.name] = {"columns": reader.fieldnames or [], "rows": 0}
        for row in reader:
            data["files"][partners_path.name]["rows"] += 1
            if (row.get("PARVW") or "").strip().upper() != "SH":
                continue
            soldto = (row.get("SOLDTO") or "").strip()
            if not soldto:
                continue
            partner = party_from_row(row, "SHIPTO")
            data["partners_by_soldto"].setdefault(soldto, []).append(partner)
            if partner["postal"]:
                data["partners_by_postal"].setdefault(partner["postal"], []).append((soldto, partner))
            # Index by agency code (from name like ".ISERBA (STQ)")
            _pn = partner.get("name", "")
            _lp = _pn.find("(")
            _rp = _pn.find(")", _lp + 1) if _lp >= 0 else -1
            _agency_code_str = _pn[_lp+1:_rp] if _lp >= 0 and _rp > _lp else ""
            if _agency_code_str and _agency_code_str.isalpha() and _agency_code_str.isupper() and 2 <= len(_agency_code_str) <= 5:
                data["partners_by_agency"].setdefault(_agency_code_str, []).append(partner)
            # Index by normalized city
            _city_norm = _normalize_for_index(partner.get("city", ""))
            if _city_norm and len(_city_norm) > 2:
                data["partners_by_normalized_city"].setdefault(_city_norm, []).append((soldto, partner))
            # Index by normalized street
            _street_norm = _normalize_for_index(partner.get("street", ""))
            if _street_norm and len(_street_norm) > 4:
                data["partners_by_normalized_street"].setdefault(_street_norm, []).append((soldto, partner))

    if materials_path.exists():
        with open_master_csv(materials_path) as handle:
            reader = csv.DictReader(handle, delimiter=";")
            data["files"][materials_path.name] = {"columns": reader.fieldnames or [], "rows": 0}
            for row in reader:
                data["files"][materials_path.name]["rows"] += 1
                material_id = (row.get("MATNR") or "").strip()
                description = (row.get("MAKTX") or "").strip()
                if material_id and description:
                    data["materials_by_id"][material_id] = description
        data["materials_count"] = data["files"][materials_path.name]["rows"]

    if salesorders_path.exists():
        with open_master_csv(salesorders_path) as handle:
            reader = csv.DictReader(handle, delimiter=";")
            data["files"][salesorders_path.name] = {"columns": reader.fieldnames or [], "rows": 0}
            for row in reader:
                data["files"][salesorders_path.name]["rows"] += 1
                bstnk = norm_order_key(row.get("BSTNK") or "")
                kunnr = (row.get("KUNNR") or "").strip()
                if not bstnk or not kunnr:
                    continue
                record = {
                    "bstnk": bstnk,
                    "kunnr": kunnr,
                    "vbeln": (row.get("VBELN") or "").strip(),
                    "erdat": (row.get("ERDAT") or "").strip(),
                }
                data["salesorders_by_bstnk"].setdefault(bstnk, []).append(record)
                data["salesorders_by_kunnr"].setdefault(kunnr, []).append(record)
        data["salesorders_count"] = data["files"][salesorders_path.name]["rows"]

    data["loaded"] = True
    master_data_cache = data
    master_data_cache_fingerprint = fingerprint
    return data


def lookup_customer_by_order_number(data: dict[str, Any], order_number: str | None) -> dict | None:
    if not order_number:
        return None
    key = norm_order_key(order_number)
    records = data.get("salesorders_by_bstnk", {}).get(key, [])
    if not records:
        return None
    records = sorted(records, key=lambda item: item.get("erdat", ""), reverse=True)
    kunnr = records[0]["kunnr"]
    customer = data.get("customers_by_id", {}).get(kunnr)
    if not customer:
        return None
    buyer = dict(customer)
    cfg = scoring_config()
    buyer["_score"] = cfg["buyer_order_lookup_score"]
    buyer["_reason"] = f"bstnk:{key}+kunnr:{kunnr}"
    buyer["_order_vbeln"] = records[0].get("vbeln", "")
    return buyer


def validate_order_number(
    data: dict[str, Any],
    order_number: str | None,
    soldto_id: str | None = None,
) -> dict:
    if not order_number:
        return {
            "Statut": "Non detecte",
            "BSTNK": "",
            "KUNNR": "",
            "VBELN": "",
            "ERDAT": "",
        }

    key = norm_order_key(order_number)
    records = data.get("salesorders_by_bstnk", {}).get(key, [])
    if not records:
        return {
            "Statut": "Non trouvee master data",
            "BSTNK": key,
            "KUNNR": "",
            "VBELN": "",
            "ERDAT": "",
        }

    record = sorted(records, key=lambda item: item.get("erdat", ""), reverse=True)[0]
    kunnr = record["kunnr"]
    status = "Confirmee master data"
    if soldto_id and soldto_id != kunnr:
        status = "Conflit SOLDTO"
    customer = data.get("customers_by_id", {}).get(kunnr, {})
    return {
        "Statut": status,
        "BSTNK": key,
        "KUNNR": kunnr,
        "Client masterdata": customer.get("name", ""),
        "VBELN": record.get("vbeln", ""),
        "ERDAT": record.get("erdat", ""),
        "Occurrences": len(records),
    }


def supplier_header_vats(text: str) -> set[str]:
    import re

    header = fold_text(text[:2500])
    markers = ("siege social", "rcs", "iban", "siret", "capital de")
    if not any(marker in header for marker in markers):
        return set()
    return {
        norm_vat(value)
        for value in re.findall(r"\b[A-Z]{2}\s?[A-Z0-9]{2}(?:\s?\d){9,12}\b", text[:2500], flags=re.IGNORECASE)
    }


def collect_buyer_candidates(
    data: dict[str, Any],
    text: str,
    fields: dict,
    filename: str | None,
    delivery: dict | None = None,
) -> list[dict]:
    from app.delivery import extract_billing_postal_hints

    vats = {norm_vat(value) for value in fields.get("vat_numbers", []) if value}
    vats -= supplier_header_vats(text)
    candidate_ids: set[str] = set()

    for vat in vats:
        for customer in data.get("customers_by_vat", {}).get(vat, []):
            candidate_ids.add(customer["id"])

    postal_sources = extract_billing_postal_hints(text)
    if delivery and delivery.get("Code postal"):
        postal_sources.append(norm_postal(delivery["Code postal"]))
    postal_sources.extend(extract_postal_codes(text[:12000]))

    seen_postals: set[str] = set()
    for postal in postal_sources:
        postal = norm_postal(postal)
        if not postal or postal in seen_postals:
            continue
        seen_postals.add(postal)
        for customer in data.get("customers_by_postal", {}).get(postal, []):
            candidate_ids.add(customer["id"])
        for soldto, _partner in data.get("partners_by_postal", {}).get(postal, []):
            candidate_ids.add(soldto)
        for customer in data.get("customers", []):
            if postal_compatible(postal, customer.get("postal", "")):
                candidate_ids.add(customer["id"])

    if not candidate_ids:
        return list(data.get("customers", []))
    return [data["customers_by_id"][customer_id] for customer_id in candidate_ids if customer_id in data["customers_by_id"]]


def score_buyer_delivery_address(data: dict[str, Any], customer: dict, delivery: dict | None) -> tuple[int, list[str]]:
    if not delivery:
        return 0, []

    postal = norm_postal(delivery.get("Code postal") or "")
    city = delivery.get("Ville") or ""
    street = delivery.get("Rue") or ""
    if not (postal or city or street):
        return 0, []

    cfg = scoring_config()
    best_score = 0
    best_reasons: list[str] = []

    customer_postal = norm_postal(customer.get("postal") or "")
    customer_city = customer.get("city") or ""
    customer_street = customer.get("street") or ""
    if street and postal and customer_postal == postal and city_compatible(city, customer_city):
        ratio = street_similarity(street, customer_street)
        if ratio >= cfg["street_exact_ratio"]:
            return 120, ["delivery_soldto_billing_exact", "postal_exact", "city"]
        if ratio >= cfg["street_fuzzy_ratio"]:
            return 70, ["delivery_soldto_billing_fuzzy", "postal_exact", "city"]

    for row in data.get("partners_by_soldto", {}).get(customer.get("id"), []):
        score = 0
        reasons = []
        row_postal = norm_postal(row.get("postal") or "")
        postal_ok = bool(postal and row_postal == postal)
        city_ok = bool(city and city_compatible(city, row.get("city", "")))
        if postal_ok:
            score += 35
            reasons.append("delivery_postal")
        elif postal and postal_compatible(postal, row_postal):
            score += 20
            reasons.append("delivery_postal_proche")
        if city_ok:
            score += 25
            reasons.append("delivery_city")
        if street and postal_ok and city_ok:
            ratio = street_similarity(street, row.get("street", ""))
            if ratio >= cfg["street_exact_ratio"]:
                score += 75
                reasons.append("delivery_street_exactish")
            elif ratio >= cfg["street_fuzzy_ratio"]:
                score += 35
                reasons.append("delivery_street_fuzzy")
        if row is not customer and score:
            score += 15
            reasons.append(f"delivery_shipto:{row.get('id')}")
        if score > best_score:
            best_score = score
            best_reasons = reasons
    return best_score, best_reasons


def score_buyer_candidate(
    customer: dict,
    text: str,
    fields: dict,
    filename: str | None,
    delivery: dict | None = None,
    data: dict[str, Any] | None = None,
) -> tuple[int, list[str]]:
    vats = {norm_vat(value) for value in fields.get("vat_numbers", []) if value}
    vats -= supplier_header_vats(text)
    haystack_text = norm_name(text[:8000])
    score = 0
    reasons = []

    if customer.get("vat") and customer["vat"] in vats:
        score += 100
        reasons.append(f"vat:{customer['vat']}")

    name = norm_name(customer.get("name", ""))
    if name and name in haystack_text:
        score += 35
        reasons.append("name_text")

    postal = customer.get("postal", "")
    city = norm_name(customer.get("city", ""))
    if postal and postal in haystack_text:
        score += 10
        reasons.append("postal_text")
    if city and city in haystack_text:
        score += 10
        reasons.append("city_text")

    if data is not None:
        delivery_score, delivery_reasons = score_buyer_delivery_address(data, customer, delivery)
        if delivery_score:
            score += delivery_score
            reasons.extend(delivery_reasons)

    return score, reasons


def infer_buyer_from_master(
    data: dict[str, Any],
    text: str,
    fields: dict,
    filename: str | None,
    order_number: str | None = None,
    delivery: dict | None = None,
) -> dict | None:
    cfg = scoring_config()

    buyer = lookup_customer_by_order_number(data, order_number)
    if buyer:
        return buyer

    candidates = collect_buyer_candidates(data, text, fields, filename, delivery)
    best = None
    best_score = 0
    second_score = 0
    best_reasons = []
    ranked = []

    for customer in candidates:
        score, reasons = score_buyer_candidate(customer, text, fields, filename, delivery, data)
        ranked.append({"id": customer["id"], "name": customer["name"], "score": score, "reasons": reasons})
        if score > best_score:
            second_score = best_score
            best = customer
            best_score = score
            best_reasons = reasons
        elif score > second_score:
            second_score = score

    if best and best_score >= cfg["buyer_min_score"] and (
        best_score - second_score >= cfg["buyer_min_margin"] or best_score >= cfg["buyer_vat_auto_score"]
    ):
        result = dict(best)
        result["_score"] = best_score
        result["_reason"] = "+".join(best_reasons)
        result["_buyer_candidates"] = sorted(ranked, key=lambda item: item["score"], reverse=True)[:5]
        return result
    return None


def city_compatible(a: str, b: str) -> bool:
    from app.text_utils import normalize_address_compare

    a_key = norm_key(normalize_address_compare(a))
    b_key = norm_key(normalize_address_compare(b))
    return bool(a_key and b_key and (a_key == b_key or a_key.startswith(b_key) or b_key.startswith(a_key)))


def postal_compatible(a: str, b: str) -> bool:
    a_postal = norm_postal(a)
    b_postal = norm_postal(b)
    if not a_postal or not b_postal:
        return False
    if a_postal == b_postal:
        return True
    return len(a_postal) == 5 and len(b_postal) == 5 and a_postal[:3] == b_postal[:3]


def street_similarity(a: str, b: str) -> float:
    from app.street_types import normalize_street_for_match
    from app.text_utils import normalize_address_compare

    a_key = normalize_street_for_match(normalize_address_compare(a))
    b_key = normalize_street_for_match(normalize_address_compare(b))
    if not a_key or not b_key:
        return 0.0
    return SequenceMatcher(None, a_key, b_key).ratio()


def score_layout_candidate_against_partner(partner: dict, candidate: dict) -> tuple[int, list[str]]:
    cfg = scoring_config()
    score = 0
    reasons = []
    postal = norm_postal(candidate.get("Code postal") or "")
    city = candidate.get("Ville") or ""
    street = candidate.get("Rue") or ""

    if postal and postal == partner.get("postal"):
        score += 35
        reasons.append("postal_layout")
    if city and city_compatible(city, partner.get("city", "")):
        score += 25
        reasons.append("city_layout")

    street_ratio = street_similarity(street, partner.get("street", ""))
    if street_ratio >= cfg["street_exact_ratio"]:
        score += 25
        reasons.append("street_layout")
    elif street_ratio >= cfg["street_fuzzy_ratio"]:
        score += 12
        reasons.append("street_layout_fuzzy")

    strong_address_match = postal == partner.get("postal") or street_ratio >= cfg["street_fuzzy_ratio"]
    if strong_address_match and score >= 35:
        geo_bonus = int(min(30, max(0, candidate.get("Score geometrie", 0)) * cfg["layout_geo_bonus_factor"]))
        if geo_bonus:
            score += geo_bonus
            reasons.append("geo_bonus")
    else:
        score = 0
        reasons = []
    return score, reasons


def score_partner_service_name(partner: dict, delivery: dict) -> tuple[int, list[str]]:
    service = delivery.get("Nom / service") or ""
    if not service:
        return 0, []

    cfg = scoring_config()
    service_key = norm_key(service)
    partner_name = norm_key(partner.get("name", ""))
    score = 0
    reasons = []

    if service_key and (service_key in partner_name or partner_name in service_key):
        score += int(cfg.get("shipto_service_name_score", 40))
        reasons.append("service_name")
        return score, reasons

    tokens = significant_tokens(service)
    matched = [token for token in tokens if token in partner_name]
    if len(matched) >= 2:
        score += int(cfg.get("shipto_service_tokens_score", 30))
        reasons.append("service_tokens")
    elif len(matched) == 1:
        score += 15
        reasons.append("service_token")
    return score, reasons


def delivery_has_precise_postal_address(delivery: dict) -> bool:
    return bool(delivery.get("Rue") and (delivery.get("Code postal") or delivery.get("Ville")))


def score_shipto(
    partner: dict,
    delivery: dict,
    filename: str | None,
    text: str = "",
    layout_candidates: list[dict] | None = None,
) -> tuple[int, list[str], dict | None]:
    import re

    cfg = scoring_config()
    score = 0
    reasons = []
    site = norm_key(delivery.get("Site") or "")
    partner_name = norm_name(partner.get("name", ""))
    best_layout_match = None

    if site and site in norm_key(partner_name):
        score += 45
        reasons.append(f"site:{site}")

    postal = norm_postal(delivery.get("Code postal") or "")
    city = delivery.get("Ville") or ""
    street = delivery.get("Rue") or ""
    has_delivery_anchor = bool(site or postal or city or street)
    if postal and postal == partner.get("postal"):
        score += 45
        reasons.append("postal")
    elif postal and postal_compatible(postal, partner.get("postal", "")):
        score += 30
        reasons.append("postal_proche")
    if city and city_compatible(city, partner.get("city", "")):
        score += 35
        reasons.append("city")
    if street:
        ratio = street_similarity(street, partner.get("street", ""))
        if ratio >= cfg["street_exact_ratio"]:
            score += 30
            reasons.append("street_exactish")
        elif ratio >= cfg["street_fuzzy_ratio"]:
            score += 15
            reasons.append("street_fuzzy")

    service_score, service_reasons = score_partner_service_name(partner, delivery)
    if service_score and not delivery_has_precise_postal_address(delivery):
        score += service_score
        reasons.extend(service_reasons)

    if not has_delivery_anchor and text:
        from app.text_utils import compact_text

        text_window = compact_text(text[:12000])
        text_key = norm_key(text_window)
        partner_postal = partner.get("postal", "")
        partner_city = partner.get("city", "")
        partner_street = partner.get("street", "")
        if partner_postal and re.search(rf"\b{re.escape(partner_postal)}\b", text_window):
            score += 45
            reasons.append("postal_text")
            if partner_city and norm_key(partner_city) in text_key:
                score += 35
                reasons.append("city_text")
            if partner_street and norm_key(partner_street) in text_key:
                score += 30
                reasons.append("street_text")

    best_layout_score = 0
    best_layout_reasons = []
    for candidate in layout_candidates or []:
        candidate_score, candidate_reasons = score_layout_candidate_against_partner(partner, candidate)
        if candidate_score > best_layout_score:
            best_layout_score = candidate_score
            best_layout_reasons = candidate_reasons
            best_layout_match = {
                "Adresse candidate": candidate.get("Adresse complete", ""),
                "Score candidat": candidate.get("Score geometrie", 0),
                "Score match": candidate_score,
                "Raisons": "+".join(candidate_reasons),
                "Code postal": candidate.get("Code postal", ""),
                "Ville": candidate.get("Ville", ""),
                "Rue": candidate.get("Rue", ""),
                "Ancre positive": candidate.get("Ancre positive", ""),
                "Ancre negative": candidate.get("Ancre negative", ""),
            }
    if best_layout_score:
        score += best_layout_score
        reasons.extend(best_layout_reasons)
    return score, reasons, best_layout_match


def filter_shipto_candidates(partners: list[dict], delivery: dict, *, allow_fallback: bool = True) -> list[dict]:
    postal = norm_postal(delivery.get("Code postal") or "")
    city = delivery.get("Ville") or ""
    if not postal and not city:
        return partners

    filtered = []
    for partner in partners:
        if postal and partner.get("postal") == postal:
            filtered.append(partner)
            continue
        if allow_fallback and postal and postal_compatible(postal, partner.get("postal", "")):
            filtered.append(partner)
            continue
        if city and city_compatible(city, partner.get("city", "")):
            filtered.append(partner)
    if filtered:
        return filtered
    return partners if allow_fallback else []


def candidate_to_delivery(address: dict) -> dict:
    skip = {"Source", "Score resolution"}
    return {key: value for key, value in address.items() if key not in skip}


def filter_candidates_to_primary_detection(candidates: list[dict], primary: dict) -> list[dict]:
    primary_postal = norm_postal(primary.get("Code postal") or "")
    primary_city = primary.get("Ville") or ""
    primary_score = int(primary.get("Score resolution") or primary.get("Score geometrie") or 0)
    if primary_score < 80 or not (primary_postal or primary_city):
        return candidates

    filtered = []
    for candidate in candidates:
        candidate_postal = norm_postal(candidate.get("Code postal") or "")
        candidate_city = candidate.get("Ville") or ""
        if primary_postal and candidate_postal == primary_postal:
            filtered.append(candidate)
            continue
        if primary_city and city_compatible(primary_city, candidate_city):
            filtered.append(candidate)
    return filtered or candidates


def is_clear_match_winner(matches: list[tuple], min_margin: int | None = None) -> bool:
    if not matches:
        return False
    if len(matches) == 1:
        return True
    margin = min_margin
    if margin is None:
        margin = int(scoring_config().get("shipto_min_margin", 15))
    return matches[0][0] - matches[1][0] >= margin


def soldto_ids_from_document(text: str) -> set[str]:
    import re

    soldtos: set[str] = set()
    patterns = [
        r"(?:n[°o]?\s*client|client\s*n[°o]?|numero\s+client|customer\s+no)\s*:?\s*(1\d{7})\b",
        r"\b(1\d{7})\b",
    ]
    compact = text[:6000]
    for pattern in patterns[:1]:
        for match in re.finditer(pattern, compact, flags=re.IGNORECASE):
            soldtos.add(match.group(1))
    for line in compact.splitlines():
        folded = fold_text(line)
        if any(token in folded for token in ("n client", "no client", "numero client", "n° client")):
            for match in re.finditer(r"\b(1\d{7})\b", line):
                soldtos.add(match.group(1))
    return soldtos


def apply_soldto_hint_boost(
    matches: list[tuple[int, list[str], str, Any]],
    *,
    known_soldto_id: str | None,
    order_soldto_id: str | None,
    vat_soldtos: set[str],
    document_soldtos: set[str],
) -> list[tuple[int, list[str], str, Any]]:
    if not matches:
        return matches
    boosted: list[tuple[int, list[str], str, Any]] = []
    hint_ids = set(document_soldtos)
    if known_soldto_id:
        hint_ids.add(known_soldto_id)
    if order_soldto_id:
        hint_ids.add(order_soldto_id)
    hint_ids.update(vat_soldtos)
    for score, reasons, soldto_id, payload in matches:
        total_score = score
        total_reasons = list(reasons)
        if soldto_id in hint_ids:
            total_score += 25
            total_reasons.append("soldto_hint")
        boosted.append((total_score, total_reasons, soldto_id, payload))
    boosted.sort(key=lambda item: item[0], reverse=True)
    return boosted


def delivery_partner_postal_keys(postal: str, city: str) -> set[str]:
    from app.postal_reference import postals_for_city

    keys = {norm_postal(postal)}
    for alt in postals_for_city(city):
        keys.add(norm_postal(alt))
    return {item for item in keys if item}


def best_matching_partner_for_soldto(
    data: dict[str, Any],
    soldto_id: str,
    delivery: dict,
) -> dict | None:
    cfg = scoring_config()
    street = delivery.get("Rue") or ""
    city = delivery.get("Ville") or ""
    postal = norm_postal(delivery.get("Code postal") or "")
    if not soldto_id or not street:
        return None

    best_partner: dict | None = None
    best_score = -1
    for partner in data.get("partners_by_soldto", {}).get(soldto_id, []):
        if city and not city_compatible(city, partner.get("city", "")):
            continue
        ratio = street_similarity(street, partner.get("street", ""))
        if ratio < cfg["street_fuzzy_ratio"]:
            continue
        score = int(ratio * 100)
        partner_postal = norm_postal(partner.get("postal", ""))
        if partner_postal == postal:
            score += 35
        elif postal_compatible(postal, partner_postal):
            score += 15
        if score > best_score:
            best_score = score
            best_partner = partner
    return best_partner


def soldto_billing_matches_by_address(
    data: dict[str, Any],
    delivery: dict,
) -> list[tuple[int, list[str], str, dict]]:
    postal = norm_postal(delivery.get("Code postal") or "")
    city = delivery.get("Ville") or ""
    street = delivery.get("Rue") or ""
    if not (postal and city and street):
        return []

    cfg = scoring_config()
    matches: list[tuple[int, list[str], str, dict]] = []
    seen: set[str] = set()
    candidates = list(data.get("customers_by_postal", {}).get(postal, []))
    for customer in data.get("customers", []):
        if postal_compatible(postal, customer.get("postal", "")):
            candidates.append(customer)

    for customer in candidates:
        soldto_id = customer.get("id", "")
        if not soldto_id or soldto_id in seen:
            continue
        if norm_postal(customer.get("postal", "")) != postal:
            continue
        if not city_compatible(city, customer.get("city", "")):
            continue
        ratio = street_similarity(street, customer.get("street", ""))
        if ratio < cfg["street_fuzzy_ratio"]:
            continue

        score = 90
        reasons = ["soldto_billing_address", "postal_exact", "city"]
        if ratio >= cfg["street_exact_ratio"]:
            score += 25
            reasons.append("street_exactish")
        else:
            score += 10
            reasons.append("street_fuzzy")
        matches.append((score, reasons, soldto_id, customer))
        seen.add(soldto_id)

    matches.sort(key=lambda item: item[0], reverse=True)
    return matches


def customer_as_delivery_partner(customer: dict) -> dict:
    return {
        "id": customer.get("id", ""),
        "name": customer.get("name", ""),
        "street": customer.get("street", ""),
        "city": customer.get("city", ""),
        "postal": customer.get("postal", ""),
        "country": customer.get("country", "FR"),
    }


def build_soldto_billing_result(
    *,
    data: dict[str, Any],
    matches: list[tuple[int, list[str], str, dict]],
    layout_analysis: dict | None,
    detected_candidate: dict,
    filename: str | None = None,
) -> tuple[dict, dict]:
    best_score, best_reasons, best_soldto, customer = matches[0]
    buyer = dict(customer)
    buyer["_score"] = best_score
    buyer["_reason"] = "+".join(best_reasons)
    buyer["_buyer_candidates"] = [
        {
            "id": soldto,
            "name": payload.get("name", ""),
            "score": score,
            "reasons": reasons,
        }
        for score, reasons, soldto, payload in matches[:5]
    ]
    partner = customer_as_delivery_partner(customer)
    second_score = matches[1][0] if len(matches) > 1 else -1
    detected = candidate_to_delivery(detected_candidate)
    shipto_partner = best_matching_partner_for_soldto(data, best_soldto, detected)
    if shipto_partner and shipto_partner.get("id") != best_soldto:
        partner = shipto_partner
    detected["Source retenue"] = detected_candidate.get("Source", detected_candidate.get("Source retenue", ""))
    detected["Score resolution"] = detected_candidate.get("Score resolution", detected_candidate.get("Score geometrie", 0))
    detected["Guidage masterdata"] = "oui"
    validated = build_validated_delivery_result(
        buyer=buyer,
        best_partner=partner,
        best_score=best_score,
        second_score=second_score,
        best_reasons=best_reasons,
        best_layout_match=None,
        layout_analysis=layout_analysis,
        scored_partners=[(score, reasons, customer_as_delivery_partner(payload), None) for score, reasons, _sid, payload in matches],
        guided=True,
        detected_candidate=detected_candidate,
    )
    validated["Strategie matching"] = "adresse_soldto_facturation"
    if shipto_partner and shipto_partner.get("id") != best_soldto:
        validated["SHIPTO"] = shipto_partner.get("id", "")
        validated["Livraison egale facturation SOLDTO"] = "non"
        validated["Nom"] = shipto_partner.get("name", validated.get("Nom"))
        validated["Rue"] = shipto_partner.get("street", validated.get("Rue"))
        validated["Code postal"] = shipto_partner.get("postal", validated.get("Code postal"))
        validated["Ville"] = shipto_partner.get("city", validated.get("Ville"))
    else:
        validated["SHIPTO"] = ""
        validated["Livraison egale facturation SOLDTO"] = "oui"
    return detected, validated


def rank_global_shipto_matches(
    data: dict[str, Any],
    delivery: dict,
    filename: str | None,
    text: str,
    layout_candidates: list[dict] | None,
) -> list[tuple[int, list[str], str, dict, dict | None]]:
    postal = norm_postal(delivery.get("Code postal") or "")
    city = delivery.get("Ville") or ""
    street = delivery.get("Rue") or ""
    if not postal:
        return []

    cfg = scoring_config()
    results: list[tuple[int, list[str], str, dict, dict | None]] = []
    seen: set[str] = set()
    for soldto, partner in data.get("partners_by_postal", {}).get(postal, []):
        partner_id = partner.get("id", "")
        key = f"{soldto}:{partner_id}"
        if key in seen:
            continue
        seen.add(key)
        if city and not city_compatible(city, partner.get("city", "")):
            continue
        if street:
            ratio = street_similarity(street, partner.get("street", ""))
            if ratio < cfg["street_fuzzy_ratio"]:
                continue
        score, reasons, layout_match = score_shipto(partner, delivery, filename, text, layout_candidates)
        if score <= 0:
            continue
        results.append((score, reasons, soldto, partner, layout_match))
    results.sort(key=lambda item: item[0], reverse=True)
    return results


def build_global_shipto_result(
    *,
    data: dict[str, Any],
    results: list[tuple[int, list[str], str, dict, dict | None]],
    layout_analysis: dict | None,
    detected_candidate: dict,
    strategy: str,
) -> tuple[dict, dict]:
    best_score, best_reasons, best_soldto, best_partner, best_layout_match = results[0]
    buyer = dict(data.get("customers_by_id", {}).get(best_soldto, {}))
    buyer["_score"] = best_score
    buyer["_reason"] = "+".join(best_reasons)
    buyer["_buyer_candidates"] = [
        {
            "id": soldto,
            "name": data.get("customers_by_id", {}).get(soldto, {}).get("name", ""),
            "score": score,
            "reasons": reasons,
        }
        for score, reasons, soldto, _partner, _layout in results[:5]
    ]
    second_score = results[1][0] if len(results) > 1 else -1
    detected = candidate_to_delivery(detected_candidate)
    detected["Source retenue"] = detected_candidate.get("Source", detected_candidate.get("Source retenue", ""))
    detected["Score resolution"] = detected_candidate.get("Score resolution", detected_candidate.get("Score geometrie", 0))
    detected["Guidage masterdata"] = "oui"
    validated = build_validated_delivery_result(
        buyer=buyer,
        best_partner=best_partner,
        best_score=best_score,
        second_score=second_score,
        best_reasons=best_reasons,
        best_layout_match=best_layout_match,
        layout_analysis=layout_analysis,
        scored_partners=[(score, reasons, partner, layout_match) for score, reasons, _soldto, partner, layout_match in results],
        guided=True,
        detected_candidate=detected_candidate,
    )
    validated["Strategie matching"] = strategy
    return detected, validated


def soldto_ids_from_vat(data: dict[str, Any], text: str, fields: dict) -> set[str]:
    vats = {norm_vat(value) for value in fields.get("vat_numbers", []) if value}
    vats -= supplier_header_vats(text)
    soldtos: set[str] = set()
    for vat in vats:
        for customer in data.get("customers_by_vat", {}).get(vat, []):
            soldtos.add(customer["id"])
    return soldtos


def direct_shipto_matches_by_address(
    data: dict[str, Any],
    delivery: dict,
    *,
    allowed_soldtos: set[str] | None = None,
) -> list[tuple[int, list[str], str, dict]]:
    postal = norm_postal(delivery.get("Code postal") or "")
    city = delivery.get("Ville") or ""
    street = delivery.get("Rue") or ""
    if not (postal and city and street):
        return []

    matches: list[tuple[int, list[str], str, dict]] = []
    postal_keys = delivery_partner_postal_keys(postal, city)
    seen: set[str] = set()
    for postal_key in postal_keys:
        for soldto, partner in data.get("partners_by_postal", {}).get(postal_key, []):
            partner_id = partner.get("id", "")
            key = f"{soldto}:{partner_id}"
            if key in seen:
                continue
            seen.add(key)
            if allowed_soldtos is not None and soldto not in allowed_soldtos:
                continue
            if not city_compatible(city, partner.get("city", "")):
                continue

            ratio = street_similarity(street, partner.get("street", ""))
            if ratio < scoring_config()["street_fuzzy_ratio"]:
                continue

            score = 80
            reasons = ["direct_shipto_address", "postal_exact", "city"]
            if norm_postal(partner.get("postal", "")) != postal:
                reasons = ["direct_shipto_address", "postal_compatible", "city"]
            if ratio >= scoring_config()["street_exact_ratio"]:
                score += 30
                reasons.append("street_exactish")
            else:
                score += 15
                reasons.append("street_fuzzy")
            matches.append((score, reasons, soldto, partner))

    matches.sort(key=lambda item: item[0], reverse=True)
    return matches


def prefer_shipto_matches_with_soldto_filter(
    matches: list[tuple[int, list[str], str, dict]],
    allowed_soldtos: set[str],
) -> tuple[list[tuple[int, list[str], str, dict]], bool]:
    if not matches or not allowed_soldtos:
        return matches, False

    best_score = matches[0][0]
    min_margin = int(scoring_config().get("shipto_min_margin", 15))
    close_matches = [item for item in matches if best_score - item[0] < min_margin]
    filtered = [item for item in close_matches if item[2] in allowed_soldtos]
    if not filtered:
        return matches, False

    filtered_ids = {partner.get("id") for _score, _reasons, _soldto, partner in filtered}
    remaining = [item for item in matches if item[3].get("id") not in filtered_ids]
    return [*filtered, *remaining], True


def build_direct_shipto_result(
    *,
    data: dict[str, Any],
    matches: list[tuple[int, list[str], str, dict]],
    layout_analysis: dict | None,
    detected_candidate: dict,
    filtered_by_vat: bool,
) -> tuple[dict, dict] | None:
    if not matches:
        return None
    best_score, best_reasons, best_soldto, best_partner = matches[0]
    buyer = dict(data.get("customers_by_id", {}).get(best_soldto, {}))
    if not buyer:
        return None
    buyer["_score"] = best_score
    buyer["_reason"] = "+".join([*best_reasons, "vat_soldto_filter" if filtered_by_vat else ""])
    buyer["_buyer_candidates"] = [
        {
            "id": soldto,
            "name": data.get("customers_by_id", {}).get(soldto, {}).get("name", ""),
            "score": score,
            "reasons": reasons,
        }
        for score, reasons, soldto, _partner in matches[:5]
    ]

    scored_partners = [(score, reasons, partner, None) for score, reasons, _soldto, partner in matches]
    second_score = matches[1][0] if len(matches) > 1 else -1
    detected = candidate_to_delivery(detected_candidate)
    detected["Source retenue"] = detected_candidate.get("Source", detected_candidate.get("Source retenue", ""))
    detected["Score resolution"] = detected_candidate.get("Score resolution", detected_candidate.get("Score geometrie", 0))
    detected["Guidage masterdata"] = "oui"
    validated = build_validated_delivery_result(
        buyer=buyer,
        best_partner=best_partner,
        best_score=best_score,
        second_score=second_score,
        best_reasons=best_reasons + (["vat_soldto_filter"] if filtered_by_vat else []),
        best_layout_match=None,
        layout_analysis=layout_analysis,
        scored_partners=scored_partners,
        guided=True,
        detected_candidate=detected_candidate,
    )
    validated["Strategie matching"] = "adresse_directe_shipto"
    return detected, validated


def build_validated_delivery_result(
    *,
    buyer: dict,
    best_partner: dict,
    best_score: int,
    second_score: int,
    best_reasons: list[str],
    best_layout_match: dict | None,
    layout_analysis: dict | None,
    scored_partners: list[tuple[int, list[str], dict, dict | None]],
    semantic_similarity: float | None = None,
    guided: bool = False,
    detected_candidate: dict | None = None,
) -> dict:
    cfg = scoring_config()
    top_ties = [
        partner
        for score, _reasons, partner, _layout_match in scored_partners
        if score == best_score and partner.get("id") != best_partner.get("id")
    ]
    min_margin = int(cfg.get("shipto_min_margin", 15))
    low_margin = best_score >= 0 and second_score >= 0 and (best_score - second_score) < min_margin
    ambiguous = bool(top_ties) or low_margin
    min_validated = cfg["shipto_validated_min"]
    if guided:
        min_validated = int(cfg.get("shipto_master_guided_min", min_validated))
    status = "Validee master data" if best_score >= min_validated and not ambiguous else "A verifier master data"
    if ambiguous:
        status = "A verifier master data - ambigu"
    result = {
        "Statut": status,
        "Confiance": min(100, best_score),
        "Raison": "+".join(best_reasons),
        "Ambigu": "oui" if ambiguous else "non",
        "SOLDTO": buyer["id"],
        "Client": buyer["name"],
        "Buyer score": buyer.get("_score", 0),
        "Buyer reason": buyer.get("_reason", ""),
        "Buyer candidates": buyer.get("_buyer_candidates", []),
        "Order VBELN": buyer.get("_order_vbeln", ""),
        "SHIPTO": best_partner["id"],
        "Nom": best_partner["name"],
        "Rue": best_partner["street"],
        "Code postal": best_partner["postal"],
        "Ville": best_partner["city"],
        "Pays": best_partner["country"],
        "Adresse complete": address_text(best_partner),
        "Candidat geometrie retenu": best_layout_match or {},
        "Candidats geometrie": (layout_analysis or {}).get("candidate_summaries", [])[:5],
        "Ancres geometrie": (layout_analysis or {}).get("anchor_summaries", [])[:8],
        "Autres SHIPTO ex aequo": [
            f"{partner.get('id')} - {partner.get('name')} - {partner.get('street')} - {partner.get('postal')} {partner.get('city')}"
            for partner in top_ties[:5]
        ],
        "Second SHIPTO score": second_score if second_score >= 0 else None,
        "Score marge": best_score - second_score if second_score >= 0 else best_score,
        "Guidage masterdata": "oui" if guided else "non",
    }
    if semantic_similarity is not None:
        result["Similarite semantique"] = round(semantic_similarity, 3)
    if detected_candidate:
        result["Candidat detection retenu"] = {
            "Source": detected_candidate.get("Source", ""),
            "Score resolution": detected_candidate.get("Score resolution", 0),
            "Code postal": detected_candidate.get("Code postal", ""),
            "Ville": detected_candidate.get("Ville", ""),
        }
    return result


def resolve_delivery_with_masterdata(
    text: str,
    fields: dict,
    filename: str | None,
    layout: dict | None = None,
    layout_analysis: dict | None = None,
    order_number: str | None = None,
    known_soldto_id: str | None = None,
) -> tuple[dict, dict]:
    from app.address_similarity import (
        delivery_block_text,
        embedding_score_bonus,
        is_available,
        rank_shipto_by_similarity,
    )
    from app.delivery import (
        analyze_delivery_layout,
        collect_delivery_address_candidates,
        resolve_delivery_address,
    )

    cfg = scoring_config()
    if layout_analysis is None:
        layout_analysis = analyze_delivery_layout(layout)

    candidates = collect_delivery_address_candidates(text, filename, layout, layout_analysis)
    fallback_detected = resolve_delivery_address(text, filename, layout, layout_analysis)

    data = get_master_data()
    if not data.get("loaded"):
        validated = {
            "Statut": "Master data indisponible",
            "Confiance": 0,
            "Raison": data.get("error", ""),
            "Adresse complete": "",
            "Guidage masterdata": "non",
        }
        return fallback_detected, validated

    search_candidates = candidates or [{**fallback_detected, "Source": "heuristique", "Score resolution": 0}]
    search_candidates = filter_candidates_to_primary_detection(search_candidates, fallback_detected)
    layout_candidates = (layout_analysis or {}).get("address_candidates", [])

    vat_soldtos = soldto_ids_from_vat(data, text, fields)
    document_soldtos = soldto_ids_from_document(text)
    order_buyer = lookup_customer_by_order_number(data, order_number)
    order_soldto_id = order_buyer["id"] if order_buyer else None

    def tiebreak_soldto_ids(matches: list[tuple[int, list[str], str, Any]]) -> list[tuple[int, list[str], str, Any]]:
        return apply_soldto_hint_boost(
            matches,
            known_soldto_id=known_soldto_id,
            order_soldto_id=order_soldto_id,
            vat_soldtos=vat_soldtos,
            document_soldtos=document_soldtos,
        )

    direct_candidate = search_candidates[0] if search_candidates else fallback_detected
    for candidate in search_candidates:
        delivery = candidate_to_delivery(candidate)

        shipto_matches = direct_shipto_matches_by_address(data, delivery)
        shipto_matches = tiebreak_soldto_ids(shipto_matches)
        shipto_matches, filtered_by_vat = prefer_shipto_matches_with_soldto_filter(shipto_matches, vat_soldtos)
        if shipto_matches:
            direct_candidate = candidate
            if is_clear_match_winner(shipto_matches):
                direct_result = build_direct_shipto_result(
                    data=data,
                    matches=shipto_matches,
                    layout_analysis=layout_analysis,
                    detected_candidate=direct_candidate,
                    filtered_by_vat=filtered_by_vat,
                )
                if direct_result is not None:
                    return direct_result

        soldto_matches = soldto_billing_matches_by_address(data, delivery)
        soldto_matches = tiebreak_soldto_ids(soldto_matches)
        if soldto_matches and is_clear_match_winner(soldto_matches):
            return build_soldto_billing_result(
                data=data,
                matches=soldto_matches,
                layout_analysis=layout_analysis,
                detected_candidate=candidate,
                filename=filename,
            )

        candidate_layout_candidates = filter_candidates_to_primary_detection(
            layout_candidates,
            {
                "Code postal": delivery.get("Code postal"),
                "Ville": delivery.get("Ville"),
                "Score resolution": 100,
            },
        )
        global_results = rank_global_shipto_matches(
            data,
            delivery,
            filename,
            text,
            candidate_layout_candidates,
        )
        if global_results:
            hint_ids = set(document_soldtos) | set(vat_soldtos)
            if known_soldto_id:
                hint_ids.add(known_soldto_id)
            if order_soldto_id:
                hint_ids.add(order_soldto_id)
            boosted_results = []
            for score, reasons, soldto, partner, layout_match in global_results:
                total_score = score
                total_reasons = list(reasons)
                if soldto in hint_ids:
                    total_score += 25
                    total_reasons.append("soldto_hint")
                boosted_results.append((total_score, total_reasons, soldto, partner, layout_match))
            boosted_results.sort(key=lambda item: item[0], reverse=True)
            if is_clear_match_winner(boosted_results) and boosted_results[0][0] >= int(cfg.get("shipto_master_guided_min", 55)):
                return build_global_shipto_result(
                    data=data,
                    results=boosted_results,
                    layout_analysis=layout_analysis,
                    detected_candidate=candidate,
                    strategy="adresse_globale_shipto",
                )

    primary_delivery = candidate_to_delivery(direct_candidate)
    detection_score = int(direct_candidate.get("Score resolution") or direct_candidate.get("Score geometrie") or 0)
    strong_detection = detection_score >= 80 and bool(primary_delivery.get("Code postal") and primary_delivery.get("Rue"))

    buyer = None
    if known_soldto_id and known_soldto_id in data.get("customers_by_id", {}):
        buyer = dict(data["customers_by_id"][known_soldto_id])
        buyer["_score"] = cfg["buyer_order_lookup_score"]
        buyer["_reason"] = f"known_soldto:{known_soldto_id}"
    if buyer is None and order_buyer:
        buyer = order_buyer
    if buyer is None and strong_detection:
        soldto_matches = soldto_billing_matches_by_address(data, primary_delivery)
        soldto_matches = tiebreak_soldto_ids(soldto_matches)
        if soldto_matches:
            return build_soldto_billing_result(
                data=data,
                matches=soldto_matches,
                layout_analysis=layout_analysis,
                detected_candidate=direct_candidate,
                filename=filename,
            )
    if buyer is None:
        buyer = infer_buyer_from_master(data, text, fields, filename, order_number, primary_delivery)
    if not buyer:
        validated = {
            "Statut": "Client non identifie",
            "Confiance": 0,
            "Raison": "No SOLDTO match from order/VAT/name/postal/city",
            "Adresse complete": "",
            "Guidage masterdata": "non",
        }
        detected = dict(fallback_detected)
        detected["Guidage masterdata"] = "non"
        return detected, validated

    partners = data["partners_by_soldto"].get(buyer["id"], [])
    if not partners:
        soldto_matches = soldto_billing_matches_by_address(data, primary_delivery)
        if soldto_matches and soldto_matches[0][2] == buyer["id"]:
            return build_soldto_billing_result(
                data=data,
                matches=[item for item in soldto_matches if item[2] == buyer["id"]][:1] or soldto_matches[:1],
                layout_analysis=layout_analysis,
                detected_candidate=direct_candidate,
                filename=filename,
            )
        validated = {
            "Statut": "Aucun SHIPTO master data",
            "Confiance": 0,
            "SOLDTO": buyer["id"],
            "Client": buyer["name"],
            "Raison": "No SH partner for SOLDTO",
            "Adresse complete": "",
            "Guidage masterdata": "oui",
            "Strategie matching": "soldto_sans_shipto",
        }
        detected = dict(fallback_detected)
        detected["Guidage masterdata"] = "oui"
        return detected, validated

    layout_candidates = layout_analysis.get("address_candidates", [])
    embed_weight = int(cfg.get("shipto_embedding_weight", 25))
    embed_min_sim = float(cfg.get("shipto_embedding_min_sim", 0.55))
    use_embeddings = is_available()

    best_partner = None
    best_score = -1
    second_score = -1
    best_reasons: list[str] = []
    best_layout_match = None
    best_detected_candidate: dict | None = None
    best_semantic = 0.0
    scored_partners: list[tuple[int, list[str], dict, dict | None]] = []

    for candidate in search_candidates:
        delivery = candidate_to_delivery(candidate)
        strict_address = strong_detection and bool(delivery.get("Rue"))
        filtered = filter_shipto_candidates(partners, delivery, allow_fallback=not strict_address)
        if strict_address and delivery.get("Rue"):
            street = delivery.get("Rue") or ""
            filtered = [
                partner
                for partner in filtered
                if street_similarity(street, partner.get("street", "")) >= cfg["street_fuzzy_ratio"]
                and city_compatible(delivery.get("Ville", ""), partner.get("city", ""))
            ]
        candidate_layout_candidates = filter_candidates_to_primary_detection(
            layout_candidates,
            {
                "Code postal": delivery.get("Code postal"),
                "Ville": delivery.get("Ville"),
                "Score resolution": 100,
            },
        )
        similarity_by_id: dict[str, float] = {}
        if use_embeddings and filtered:
            block = delivery_block_text(delivery)
            for partner, similarity in rank_shipto_by_similarity(block, filtered):
                similarity_by_id[partner["id"]] = similarity

        for partner in filtered:
            score, reasons, layout_match = score_shipto(
                partner, delivery, filename, text, candidate_layout_candidates
            )
            semantic = similarity_by_id.get(partner["id"], 0.0)
            bonus, applied = embedding_score_bonus(semantic, embed_weight, embed_min_sim)
            total_reasons = list(reasons)
            if applied:
                total_reasons.append(f"embedding:{semantic:.2f}")
            total_score = score + bonus
            scored_partners.append((total_score, total_reasons, partner, layout_match))
            if total_score > best_score:
                second_score = best_score
                best_partner = partner
                best_score = total_score
                best_reasons = total_reasons
                best_layout_match = layout_match
                best_detected_candidate = candidate
                best_semantic = semantic
            elif total_score > second_score:
                second_score = total_score

    if not best_partner or best_score <= 0:
        validated = {
            "Statut": "SHIPTO non identifie",
            "Confiance": 0,
            "SOLDTO": buyer["id"],
            "Client": buyer["name"],
            "Raison": "No SHIPTO compatible with detected delivery address",
            "Adresse complete": "",
            "Guidage masterdata": "oui",
        }
        detected = dict(fallback_detected)
        detected["Guidage masterdata"] = "oui"
        return detected, validated

    detected = candidate_to_delivery(best_detected_candidate or fallback_detected)
    detected["Source retenue"] = (best_detected_candidate or {}).get("Source", fallback_detected.get("Source retenue", ""))
    detected["Score resolution"] = (best_detected_candidate or {}).get(
        "Score resolution", fallback_detected.get("Score resolution", 0)
    )
    detected["Guidage masterdata"] = "oui"

    validated = build_validated_delivery_result(
        buyer=buyer,
        best_partner=best_partner,
        best_score=best_score,
        second_score=second_score,
        best_reasons=best_reasons,
        best_layout_match=best_layout_match,
        layout_analysis=layout_analysis,
        scored_partners=scored_partners,
        semantic_similarity=best_semantic if use_embeddings else None,
        guided=True,
        detected_candidate=best_detected_candidate,
    )
    return detected, validated


def validate_delivery_with_master(
    text: str,
    fields: dict,
    filename: str | None,
    delivery: dict,
    layout_analysis: dict | None = None,
    order_number: str | None = None,
    known_soldto_id: str | None = None,
) -> dict:
    cfg = scoring_config()
    data = get_master_data()
    if not data.get("loaded"):
        return {
            "Statut": "Master data indisponible",
            "Confiance": 0,
            "Raison": data.get("error", ""),
            "Adresse complete": "",
        }

    buyer = None
    if known_soldto_id and known_soldto_id in data.get("customers_by_id", {}):
        buyer = dict(data["customers_by_id"][known_soldto_id])
        buyer["_score"] = cfg["buyer_order_lookup_score"]
        buyer["_reason"] = f"known_soldto:{known_soldto_id}"
    if buyer is None:
        buyer = infer_buyer_from_master(data, text, fields, filename, order_number, delivery)
    if not buyer:
        return {
            "Statut": "Client non identifie",
            "Confiance": 0,
            "Raison": "No SOLDTO match from order/VAT/name/postal/city",
            "Adresse complete": "",
        }

    partners = data["partners_by_soldto"].get(buyer["id"], [])
    if not partners:
        return {
            "Statut": "Aucun SHIPTO master data",
            "Confiance": 0,
            "SOLDTO": buyer["id"],
            "Client": buyer["name"],
            "Raison": "No SH partner for SOLDTO",
            "Adresse complete": "",
        }

    partners = filter_shipto_candidates(partners, delivery)
    best_partner = None
    best_score = -1
    second_score = -1
    best_reasons = []
    best_layout_match = None
    scored_partners = []
    layout_candidates = (layout_analysis or {}).get("address_candidates", [])
    for partner in partners:
        score, reasons, layout_match = score_shipto(partner, delivery, filename, text, layout_candidates)
        scored_partners.append((score, reasons, partner, layout_match))
        if score > best_score:
            second_score = best_score
            best_partner = partner
            best_score = score
            best_reasons = reasons
            best_layout_match = layout_match
        elif score > second_score:
            second_score = score

    if not best_partner or best_score <= 0:
        return {
            "Statut": "SHIPTO non identifie",
            "Confiance": 0,
            "SOLDTO": buyer["id"],
            "Client": buyer["name"],
            "Adresse complete": "",
            "Guidage masterdata": "non",
        }

    return build_validated_delivery_result(
        buyer=buyer,
        best_partner=best_partner,
        best_score=best_score,
        second_score=second_score,
        best_reasons=best_reasons,
        best_layout_match=best_layout_match,
        layout_analysis=layout_analysis,
        scored_partners=scored_partners,
        guided=False,
    )
