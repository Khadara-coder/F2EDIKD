"""Master data loader for EDIFACT Orders Generator.

Loads 10564_Customers.csv, 10564_Partners.csv, 10564_Materials.csv
and optionally DB_Salesorder.csv from the authoritative
Databricks workspace masterdata folder.

Masterdata schemas (semicolon-delimited):
  Customers: SOLDTO;NAME;ORT01;PSTLZ;STRAS;LAND1;VAT_NR
  Partners:  SOLDTO;SHIPTO;LAND1;NAME;ORT01;PSTLZ;STRAS;PARVW;Fonction Partenaire;Gestionaire ADV
  Materials: MATNR;MAKTX
"""
from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .exceptions import MasterDataError

log = logging.getLogger("edifact.master_data")

# --------------------------------------------------------------------------- #
# Column alias maps  (normalised lowercase header -> logical key)
# --------------------------------------------------------------------------- #
_CUSTOMER_ALIASES: dict[str, str] = {
    "soldto": "soldto",
    "kunnr": "soldto",
    "name": "name",
    "name1": "name",
    "ort01": "city",
    "city": "city",
    "pstlz": "postal_code",
    "postal_code": "postal_code",
    "postcode": "postal_code",
    "stras": "street",
    "street": "street",
    "land1": "country",
    "country": "country",
    "vat_nr": "vat",
    "vat": "vat",
    "stnkz": "vat",
}

_PARTNER_ALIASES: dict[str, str] = {
    "soldto": "soldto",
    "kunnr": "soldto",
    "shipto": "shipto",
    "partner_id": "shipto",
    "land1": "country",
    "country": "country",
    "name": "name",
    "name1": "name",
    "ort01": "city",
    "city": "city",
    "pstlz": "postal_code",
    "postal_code": "postal_code",
    "stras": "street",
    "street": "street",
    "parvw": "partner_role",
    "partner_role": "partner_role",
    "fonction partenaire": "fonction_partenaire",
    "fonction_partenaire": "fonction_partenaire",
    "gestionaire adv": "gestionaire_adv",
    "gestionaire_adv": "gestionaire_adv",
}

_MATERIAL_ALIASES: dict[str, str] = {
    "matnr": "matnr",
    "material": "matnr",
    "material_number": "matnr",
    "maktx": "description",
    "description": "description",
    "maktg": "description",
}

_SALESORDER_ALIASES: dict[str, str] = {
    "bstnk": "bstnk",
    "order_key": "bstnk",
    "vbeln": "vbeln",
    "kunnr": "kunnr",
    "sold_to": "kunnr",
}


def _detect_delimiter(sample: str) -> str:
    """Auto-detect CSV delimiter from a sample string."""
    counts = {d: sample.count(d) for d in [";" , ",", "\t"]}
    return max(counts, key=counts.get)  # type: ignore


def _normalize_header(raw: str) -> str:
    """Lowercase, strip whitespace from column header."""
    return raw.strip().lower().lstrip("\ufeff")  # strip BOM on first column


def _read_csv_as_dicts(
    path: Path,
    alias_map: dict[str, str],
    mandatory_logical_fields: list[str],
) -> list[dict[str, str]]:
    """Read a CSV file and return list of normalised row dicts.

    All values are kept as strings with whitespace stripped.
    Leading zeros are preserved because the file is read as-is.

    Args:
        path: Path to the CSV file.
        alias_map: Maps raw column header (normalised) -> logical key.
        mandatory_logical_fields: Logical fields that must resolve; raise if absent.

    Returns:
        List of dicts keyed by logical field names.

    Raises:
        MasterDataError: If the file cannot be parsed or mandatory fields are missing.
    """
    try:
        raw_bytes = path.read_bytes()
        # Detect and strip UTF-8 BOM
        text = raw_bytes.decode("utf-8-sig", errors="replace")
    except OSError as exc:
        raise MasterDataError(f"Cannot read CSV {path}: {exc}") from exc

    sample = text[:2048]
    delim = _detect_delimiter(sample)

    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    if reader.fieldnames is None:
        raise MasterDataError(f"CSV has no headers: {path}")

    # Build header normalisation map
    header_map: dict[str, str] = {}
    for raw_col in reader.fieldnames:
        norm = _normalize_header(raw_col)
        logical = alias_map.get(norm, norm)  # fallback: keep as-is
        header_map[raw_col] = logical

    # Verify mandatory logical fields are mappable
    available_logical = set(header_map.values())
    missing = [f for f in mandatory_logical_fields if f not in available_logical]
    if missing:
        raise MasterDataError(
            f"CSV {path.name}: mandatory logical fields not found: {missing}. "
            f"Available headers: {list(reader.fieldnames)}"
        )

    rows: list[dict[str, str]] = []
    for raw_row in reader:
        row: dict[str, str] = {}
        for raw_col, value in raw_row.items():
            if raw_col is None:
                continue
            logical_key = header_map.get(raw_col, _normalize_header(raw_col))
            row[logical_key] = (value or "").strip()
        rows.append(row)

    log.info("Loaded %d rows from %s (delimiter=%r)", len(rows), path.name, delim)
    return rows


@dataclass
class MasterData:
    """Container for all loaded master-data tables."""
    customers: list[dict[str, str]] = field(default_factory=list)
    partners: list[dict[str, str]] = field(default_factory=list)
    materials: dict[str, str] = field(default_factory=dict)  # matnr -> description
    salesorders: list[dict[str, str]] = field(default_factory=list)

    # Materialset for fast membership check
    _material_set: frozenset[str] = field(default_factory=frozenset, init=False, repr=False)

    def __post_init__(self) -> None:
        self._material_set = frozenset(self.materials.keys())

    def has_material(self, matnr: str) -> bool:
        """Return True if material exists in master data."""
        return matnr in self._material_set

    def get_customers_by_soldto(self, soldto: str) -> list[dict[str, str]]:
        """Return all customer rows matching a given SOLDTO number."""
        return [c for c in self.customers if c.get("soldto") == soldto]

    def get_partners_by_soldto(self, soldto: str) -> list[dict[str, str]]:
        """Return all partner rows for a given SOLDTO."""
        return [p for p in self.partners if p.get("soldto") == soldto]


def load_master_data(
    customers_csv: str,
    partners_csv: str,
    materials_csv: str,
    salesorder_csv: str = "",
) -> MasterData:
    """Load all master-data CSV files and return a MasterData container.

    Args:
        customers_csv: Path to 10564_Customers.csv.
        partners_csv: Path to 10564_Partners.csv.
        materials_csv: Path to 10564_Materials.csv.
        salesorder_csv: Optional path to DB_Salesorder.csv.

    Returns:
        MasterData container.

    Raises:
        MasterDataError: If mandatory files are missing or columns cannot be resolved.
    """
    for label, path_str in [
        ("customers", customers_csv),
        ("partners", partners_csv),
        ("materials", materials_csv),
    ]:
        if not Path(path_str).exists():
            raise MasterDataError(
                f"Mandatory master-data file missing [{label}]: {path_str}"
            )

    customers = _read_csv_as_dicts(
        Path(customers_csv),
        _CUSTOMER_ALIASES,
        ["soldto", "name"],
    )

    partners = _read_csv_as_dicts(
        Path(partners_csv),
        _PARTNER_ALIASES,
        ["soldto", "shipto"],
    )

    mat_rows = _read_csv_as_dicts(
        Path(materials_csv),
        _MATERIAL_ALIASES,
        ["matnr"],
    )
    materials: dict[str, str] = {
        row["matnr"]: row.get("description", "") for row in mat_rows if row.get("matnr")
    }
    log.info("Materials index built: %d unique MATNRs", len(materials))

    salesorders: list[dict[str, str]] = []
    if salesorder_csv and Path(salesorder_csv).exists():
        try:
            salesorders = _read_csv_as_dicts(
                Path(salesorder_csv),
                _SALESORDER_ALIASES,
                [],  # no mandatory fields: optional file
            )
            log.info(
                "DB_Salesorder loaded: %d rows (reference only, not used for order override)",
                len(salesorders),
            )
        except MasterDataError as exc:
            log.warning("Could not load DB_Salesorder.csv (non-fatal): %s", exc)
    elif salesorder_csv:
        log.info("DB_Salesorder.csv not found at %s (optional, continuing)", salesorder_csv)

    md = MasterData(
        customers=customers,
        partners=partners,
        materials=materials,
        salesorders=salesorders,
    )
    log.info(
        "Master data loaded: customers=%d partners=%d materials=%d salesorders=%d",
        len(customers), len(partners), len(materials), len(salesorders),
    )
    return md
