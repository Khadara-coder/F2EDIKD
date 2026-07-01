from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any, Optional


# ============================================================
# Exceptions
# ============================================================

class EdifactBuildError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("EDIFACT build failed: " + "; ".join(errors))


# ============================================================
# Data models
# ============================================================

@dataclass
class Party:
    sap_code: str
    name: str
    address_line_1: str
    city: str
    postal_code: str
    country_code: str = "FR"


@dataclass
class OrderLine:
    article_code: str
    quantity: Any
    unit_price: Any
    description: Optional[str] = None
    delivery_date: Optional[str] = None


@dataclass
class Order:
    po_number: str
    document_date: str
    buyer: Party
    ship_to: Party
    lines: list[OrderLine]
    delivery_date: Optional[str] = None
    express: bool = False


# ============================================================
# Constants Bosch / Esker
# ============================================================

SENDER_GLN = "4399901876613"      # Esker EDI
RECEIVER_GLN = "3015981600108"    # ELM LEBLANC SAS / Bosch France

IGNORED_ARTICLE_PATTERNS = (
    "PORT",
    "PORTSFAB",
    "PORT FOURNISSEUR",
    "ECOTAX",
    "ECOTAXE",
    "FRAIS DE PORT",
    "PARTICIPATION TRANSPORT",
)


# ============================================================
# Helpers
# ============================================================

def clean_text(value: Any) -> str:
    """Nettoyage texte simple pour EDIFACT."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clean_postal(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def edifact_escape(value: Any) -> str:
    """
    Escape EDIFACT avec release character '?'.
    Service chars UNA:+.? '
    """
    s = clean_text(value)
    s = s.replace("?", "??")
    s = s.replace("+", "?+")
    s = s.replace(":", "?:")
    s = s.replace("'", "?'")
    return s


def parse_date_to_ccyymmdd(value: Any) -> Optional[str]:
    """
    Convertit :
    - 26/06/2026 -> 20260626
    - 26-06-2026 -> 20260626
    - 2026-06-26 -> 20260626
    - 20260626 -> 20260626
    """
    raw = clean_text(value)
    if not raw:
        return None

    # dd/mm/yyyy ou dd-mm-yyyy ou dd.mm.yyyy
    m = re.match(r"^(\d{2})[/.-](\d{2})[/.-](\d{4})$", raw)
    if m:
        dd, mm, yyyy = m.groups()
        return validate_date_parts(yyyy, mm, dd)

    # yyyy/mm/dd ou yyyy-mm-dd ou yyyy.mm.dd
    m = re.match(r"^(\d{4})[/.-](\d{2})[/.-](\d{2})$", raw)
    if m:
        yyyy, mm, dd = m.groups()
        return validate_date_parts(yyyy, mm, dd)

    digits = re.sub(r"\D", "", raw)

    # YYYYMMDD
    if re.match(r"^\d{8}$", digits):
        yyyy, mm, dd = digits[:4], digits[4:6], digits[6:8]
        valid = validate_date_parts(yyyy, mm, dd)
        if valid:
            return valid

        # DDMMYYYY
        dd, mm, yyyy = digits[:2], digits[2:4], digits[4:8]
        return validate_date_parts(yyyy, mm, dd)

    return None


def validate_date_parts(yyyy: str, mm: str, dd: str) -> Optional[str]:
    try:
        datetime(int(yyyy), int(mm), int(dd))
        return f"{yyyy}{mm}{dd}"
    except ValueError:
        return None


def format_decimal(value: Any, scale: int = 6) -> Optional[str]:
    """
    Convertit les nombres francais/anglais :
    - "10,5" -> "10.5"
    - "1 234,50" -> "1234.5"
    """
    if value is None or value == "":
        return None

    raw = str(value).strip()
    raw = raw.replace(" ", "").replace("\u00a0", "")

    # Cas francais : 1.234,56 -> 1234.56
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", ".")

    try:
        d = Decimal(raw)
    except InvalidOperation:
        return None

    if d <= 0:
        return None

    quant = Decimal("1." + ("0" * scale))
    d = d.quantize(quant, rounding=ROUND_HALF_UP)

    s = format(d, "f")
    s = s.rstrip("0").rstrip(".")
    return s or None


def normalize_article_code(value: Any) -> tuple[Optional[str], Optional[str], bool]:
    """
    Retourne : article_code, error_code, ignore_line

    Regles :
    - ignore PORT / ECOTAXE / PORT FOURNISSEUR
    - supprime prefixe EL
    - supprime espaces et tirets
    - impose un code alphanumerique 1 a 13 caracteres
    """
    raw = clean_text(value).upper()

    if not raw:
        return None, "ARTICLE_MISSING", False

    for pattern in IGNORED_ARTICLE_PATTERNS:
        if raw.startswith(pattern):
            return None, None, True

    code = raw
    code = re.sub(r"^EL\s*", "", code)
    code = re.sub(r"[\s\-]", "", code)

    if not re.fullmatch(r"[A-Z0-9]{1,13}", code):
        return code, f"ARTICLE_FORMAT_WARNING:{raw}", False

    return code, None, False


def now_yymmdd_hhmm() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    yymmdd = now.strftime("%y%m%d")
    hhmm = now.strftime("%H%M")
    return yymmdd, hhmm


# ============================================================
# Validation
# ============================================================

def validate_party(prefix: str, party: Party) -> list[str]:
    errors = []

    if not clean_text(party.sap_code):
        errors.append(f"{prefix}_SAP_CODE_MISSING")
    if not clean_text(party.name):
        errors.append(f"{prefix}_NAME_MISSING")
    if not clean_text(party.city):
        errors.append(f"{prefix}_CITY_MISSING")

    return errors


def prepare_lines(lines: list[OrderLine]) -> tuple[list[dict[str, Any]], list[str]]:
    prepared = []
    warnings = []

    if not lines:
        return [], ["NO_LINE_ITEMS"]

    for idx, line in enumerate(lines, start=1):
        article_code, article_error, ignore_line = normalize_article_code(line.article_code)

        if ignore_line:
            continue

        if article_error:
            warnings.append(f"LIN{idx}_{article_error}")

        qty = format_decimal(line.quantity)
        if not qty:
            warnings.append(f"LIN{idx}_QTY_INVALID")
            qty = "1"  # Default

        price = format_decimal(line.unit_price)
        if not price:
            warnings.append(f"LIN{idx}_UNIT_PRICE_MISSING")

        line_delivery_date = parse_date_to_ccyymmdd(line.delivery_date) if line.delivery_date else None

        if article_code:
            prepared.append({
                "article_code": article_code,
                "quantity": qty,
                "unit_price": price,
                "description": clean_text(line.description),
                "delivery_date": line_delivery_date,
            })

    if not prepared:
        warnings.append("NO_VALID_LINE_ITEMS_AFTER_FILTERING")

    return prepared, warnings


# ============================================================
# EDIFACT builder
# ============================================================

def build_orders_d96a(
    order: Order,
    interchange_ref: str,
    message_ref: str = "1",
    include_pia_1: bool = True,
) -> tuple[str, list[str]]:
    """
    Genere un EDIFACT ORDERS D96A.
    Returns (edifact_message, warnings).
    Always generates if SOLDTO+SHIPTO+PO present.
    """

    warnings = []

    po_number = clean_text(order.po_number)
    if not po_number:
        raise EdifactBuildError(["BGM_PO_NUMBER_MISSING"])

    doc_date = parse_date_to_ccyymmdd(order.document_date)
    if not doc_date:
        doc_date = datetime.now(timezone.utc).strftime("%Y%m%d")
        warnings.append("DTM_137_USING_TODAY_AS_FALLBACK")

    delivery_date = parse_date_to_ccyymmdd(order.delivery_date) if order.delivery_date else None

    party_warnings = validate_party("NAD_BY", order.buyer)
    party_warnings.extend(validate_party("NAD_DP", order.ship_to))
    warnings.extend(party_warnings)

    prepared_lines, line_warnings = prepare_lines(order.lines)
    warnings.extend(line_warnings)

    yymmdd, hhmm = now_yymmdd_hhmm()

    segments: list[str] = []

    # Interchange header
    segments.append(
        f"UNB+UNOC:3+{SENDER_GLN}+{RECEIVER_GLN}+{yymmdd}:{hhmm}+{edifact_escape(interchange_ref)}"
    )

    # Message header
    segments.append(f"UNH+{edifact_escape(message_ref)}+ORDERS:D:96A:UN")

    # Order number
    segments.append(f"BGM+220+{edifact_escape(po_number)}+9")

    # PO date
    segments.append(f"DTM+137:{doc_date}:102")

    # Delivery date
    if delivery_date:
        segments.append(f"DTM+2:{delivery_date}:102")

    if order.express:
        segments.append("FTX+AAI+++Express")

    # Buyer / Sold-To
    segments.append(
        "NAD+BY+"
        f"{edifact_escape(order.buyer.sap_code)}::91++"
        f"{edifact_escape(order.buyer.name)}+"
        f"{edifact_escape(order.buyer.address_line_1)}+"
        f"{edifact_escape(order.buyer.city)}++"
        f"{edifact_escape(clean_postal(order.buyer.postal_code))}+"
        f"{edifact_escape(order.buyer.country_code)}"
    )

    # Delivery party / Ship-To
    segments.append(
        "NAD+DP+"
        f"{edifact_escape(order.ship_to.sap_code)}::91++"
        f"{edifact_escape(order.ship_to.name)}+"
        f"{edifact_escape(order.ship_to.address_line_1)}+"
        f"{edifact_escape(order.ship_to.city)}++"
        f"{edifact_escape(clean_postal(order.ship_to.postal_code))}+"
        f"{edifact_escape(order.ship_to.country_code)}"
    )

    # Lines
    line_no = 0
    for line in prepared_lines:
        line_no += 10

        segments.append(f"LIN+{line_no}")
        segments.append(f"PIA+5+{edifact_escape(line['article_code'])}:SA::91")

        if include_pia_1:
            segments.append(f"PIA+1+{edifact_escape(line['article_code'])}:SA::91")

        if line["description"]:
            segments.append(f"IMD+A++:::{edifact_escape(line['description'][:35])}")

        segments.append(f"QTY+21:{line['quantity']}")

        if line["delivery_date"]:
            segments.append(f"DTM+2:{line['delivery_date']}:102")

        if line["unit_price"]:
            segments.append(f"PRI+AAA:{line['unit_price']}:::1")

    # Summary
    segments.append("UNS+S")
    segments.append(f"CNT+2:{len(prepared_lines)}")

    # UNT count = segments from UNH to UNT inclusive
    idx_unh = next(i for i, s in enumerate(segments) if s.startswith("UNH+"))
    unt_count = len(segments) - idx_unh + 1  # +1 for UNT itself

    segments.append(f"UNT+{unt_count}+{edifact_escape(message_ref)}")
    segments.append(f"UNZ+1+{edifact_escape(interchange_ref)}")

    # Assemble
    una = "UNA:+.? '"
    body = "\n".join(segment + "'" for segment in segments)
    edifact = una + "\n" + body

    return edifact, warnings


# ============================================================
# Adapter: extraction.py structured -> Order dataclass
# ============================================================

def build_order_from_extraction(structured: dict) -> tuple[Optional[Order], list[str]]:
    """
    Maps the structured extraction output to an Order dataclass.
    Returns: (Order or None, list of errors)
    """
    errors = []

    document = structured.get("document", {})
    adresses = structured.get("adresses", {})
    lignes = structured.get("lignes_commande", {})
    validated = adresses.get("Adresse de livraison validee", {})

    po_number = document.get("Numero de commande", "")
    if not po_number or po_number == "-":
        errors.append("PO_NUMBER_MISSING")
        return None, errors

    soldto = validated.get("SOLDTO", "")
    shipto = validated.get("SHIPTO", "")
    if not soldto or soldto == "-":
        errors.append("SOLDTO_MISSING")
        return None, errors
    if not shipto or shipto == "-":
        errors.append("SHIPTO_MISSING")
        return None, errors

    buyer = Party(
        sap_code=soldto,
        name=validated.get("Nom SOLDTO", validated.get("Nom", "")),
        address_line_1=validated.get("Adresse", ""),
        city=validated.get("Ville", ""),
        postal_code=validated.get("Code postal", ""),
        country_code="FR",
    )

    ship_to = Party(
        sap_code=shipto,
        name=validated.get("Nom", ""),
        address_line_1=validated.get("Adresse", ""),
        city=validated.get("Ville", ""),
        postal_code=validated.get("Code postal", ""),
        country_code="FR",
    )

    doc_date = (
        document.get("Date commande LLM")
        or document.get("Date document")
        or ""
    )
    delivery_date = document.get("Date livraison souhaitee")

    order_lines = []
    raw_lines = lignes.get("lignes", []) or []
    for line in raw_lines:
        order_lines.append(OrderLine(
            article_code=line.get("code_article", ""),
            quantity=line.get("quantite"),
            unit_price=line.get("prix_unitaire_ht"),
            description=line.get("description", ""),
            delivery_date=line.get("date_livraison"),
        ))

    order = Order(
        po_number=po_number,
        document_date=doc_date,
        buyer=buyer,
        ship_to=ship_to,
        lines=order_lines,
        delivery_date=delivery_date,
    )

    return order, errors


# Alias for extraction.py backward-compatibility
def structured_to_order(structured: dict):
    """Alias of build_order_from_extraction for imports in extraction.py."""
    return build_order_from_extraction(structured)
