"""Post-build EDIFACT D.96A ORDERS validator.

Validates a generated EDIFACT string against ELM_STANDARD business rules.
Returns a list of rejection codes (empty list = valid).
"""
from __future__ import annotations

import re
from typing import NamedTuple


class ValidationResult(NamedTuple):
    valid: bool
    codes: list[str]           # rejection codes from rejection_catalog
    details: list[str]         # human-readable detail per failure


# Mandatory UNB GLNs for ELM_STANDARD (immutable)
_EXPECTED_SENDER   = "4399901876613"
_EXPECTED_RECEIVER = "3015981600108"
_FORBIDDEN_STRINGS = ("3020810000707", "54209794400681", "KINETIX")


def validate_edifact(edifact: str) -> ValidationResult:
    """Validate *edifact* ORDERS D.96A string.

    Checks (in order):
      1. Forbidden profile strings absent.
      2. UNB sender/receiver GLNs.
      3. BGM+220 present with non-empty order reference.
      4. DTM+137 present with 8-digit date.
      5. NAD+BY present with buyer GLN.
      6. NAD+DP present (at least one field).
      7. At least one LIN segment.
      8. UNT segment count matches actual count.
    """
    codes:   list[str] = []
    details: list[str] = []

    if not edifact or not edifact.strip():
        return ValidationResult(False, ["EDIFACT_MISSING_BGM"], ["Empty EDIFACT string"])

    segs = [s.strip() for s in re.split(r"['\n]", edifact) if s.strip()]

    # 1. Forbidden strings
    for forbidden in _FORBIDDEN_STRINGS:
        if forbidden in edifact:
            codes.append("EDIFACT_LINE_INTEGRITY_MISMATCH")
            details.append(f"Forbidden string found: {forbidden!r}")

    # 2. UNB GLN check
    unb = next((s for s in segs if s.startswith("UNB+")), None)
    if unb:
        if _EXPECTED_SENDER not in unb:
            codes.append("EDIFACT_LINE_INTEGRITY_MISMATCH")
            details.append(f"UNB sender GLN must be {_EXPECTED_SENDER}")
        if _EXPECTED_RECEIVER not in unb:
            codes.append("EDIFACT_LINE_INTEGRITY_MISMATCH")
            details.append(f"UNB receiver GLN must be {_EXPECTED_RECEIVER}")

    # 3. BGM+220 with order reference
    bgm = next((s for s in segs if s.startswith("BGM+")), None)
    if not bgm:
        codes.append("EDIFACT_MISSING_BGM")
        details.append("BGM segment missing")
    else:
        parts = bgm.split("+")
        ref = parts[2].strip() if len(parts) > 2 else ""
        if not ref:
            codes.append("EDIFACT_MISSING_BGM")
            details.append("BGM order reference (element 3) is empty")

    # 4. DTM+137 with 8-digit date
    dtm137 = next((s for s in segs if s.startswith("DTM+137:")), None)
    if not dtm137:
        codes.append("EDIFACT_MISSING_DTM_137")
        details.append("DTM+137 document date missing")
    else:
        m = re.search(r"DTM\+137:(\d{8}):", dtm137)
        if not m:
            codes.append("EDIFACT_MISSING_DTM_137")
            details.append(f"DTM+137 date not in CCYYMMDD format: {dtm137!r}")

    # 5. NAD+BY with GLN
    nad_by = next((s for s in segs if s.startswith("NAD+BY+")), None)
    if not nad_by:
        codes.append("EDIFACT_MISSING_NAD_BY")
        details.append("NAD+BY (buyer) segment missing")
    else:
        parts = nad_by.split("+")
        gln = parts[2].split(":")[0].strip() if len(parts) > 2 else ""
        if not gln:
            codes.append("EDIFACT_MISSING_NAD_BY")
            details.append("NAD+BY buyer GLN is empty")

    # 6. NAD+DP present
    nad_dp = next((s for s in segs if s.startswith("NAD+DP+")), None)
    if not nad_dp:
        codes.append("EDIFACT_MISSING_NAD_DP")
        details.append("NAD+DP (delivery point) segment missing")

    # 7. At least one LIN
    lin_count = sum(1 for s in segs if re.match(r"^LIN\+\d+\+", s))
    if lin_count == 0:
        codes.append("EDIFACT_MISSING_LIN")
        details.append("No LIN segment found")

    # 8. UNT count integrity
    unt = next((s for s in segs if s.startswith("UNT+")), None)
    if unt:
        m = re.match(r"UNT\+(\d+)\+", unt)
        if m:
            declared = int(m.group(1))
            unh_idx  = next((i for i, s in enumerate(segs) if s.startswith("UNH+")), None)
            unt_idx  = next((i for i, s in enumerate(segs) if s.startswith("UNT+")), None)
            if unh_idx is not None and unt_idx is not None:
                actual = unt_idx - unh_idx + 1   # inclusive of UNT itself
                if declared != actual:
                    codes.append("EDIFACT_LINE_INTEGRITY_MISMATCH")
                    details.append(
                        f"UNT count mismatch: declared={declared}, actual={actual}"
                    )

    return ValidationResult(valid=(len(codes) == 0), codes=codes, details=details)
