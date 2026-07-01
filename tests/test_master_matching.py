"""Tests: Sold-to and Ship-to matching."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.matcher import match_soldto, match_shipto
from src.exceptions import MatchingError


_CUSTOMERS = [
    {
        "soldto": "15000000", "name": "ELM LEBLANC SAS", "city": "HAGUENAU",
        "postal_code": "67500", "street": "4 RUE DU DOCTEUR WILHEM SCHAEFFLER",
        "country": "FR", "vat": "FR89542097944",
    },
    {
        "soldto": "16000000", "name": "REXEL FRANCE", "city": "PARIS",
        "postal_code": "75001", "street": "10 RUE DE RIVOLI",
        "country": "FR", "vat": "FR12345678901",
    },
    {
        "soldto": "17000000", "name": "PPC SAS", "city": "BORDEAUX",
        "postal_code": "33000", "street": "5 ALLEE DES PLATANES",
        "country": "FR", "vat": "FR99999999999",
    },
]

_PARTNERS = [
    {
        "soldto": "15000000", "shipto": "15000000",
        "name": "ELM LEBLANC DEPOT HAG", "city": "HAGUENAU",
        "postal_code": "67500", "street": "4 RUE DU DOCTEUR WILHEM SCHAEFFLER",
        "country": "FR",
    },
    {
        "soldto": "15000000", "shipto": "15000010",
        "name": "ELM LEBLANC DEPOT MUL", "city": "MULHOUSE",
        "postal_code": "68100", "street": "12 RUE PASTEUR",
        "country": "FR",
    },
    {
        "soldto": "16000000", "shipto": "16000001",
        "name": "REXEL PARIS", "city": "PARIS",
        "postal_code": "75001", "street": "10 RUE DE RIVOLI",
        "country": "FR",
    },
]


class TestSoldtoMatching:
    def test_match_by_postal_and_name(self):
        result = match_soldto(
            _CUSTOMERS,
            name_query="ELM LEBLANC",
            postal_query="67500",
            city_query="HAGUENAU",
        )
        assert result["soldto"] == "15000000"

    def test_match_by_vat(self):
        result = match_soldto(
            _CUSTOMERS,
            name_query="ELM",
            vat_query="FR89542097944",
        )
        assert result["soldto"] == "15000000"

    def test_low_confidence_raises(self):
        with pytest.raises(MatchingError, match="SOLDTO_LOW_CONFIDENCE"):
            match_soldto(
                _CUSTOMERS,
                name_query="UNKNOWN COMPANY XYZ",
                postal_query="99999",
            )

    def test_empty_customers_raises(self):
        with pytest.raises(MatchingError):
            match_soldto([], name_query="ELM LEBLANC")


class TestShiptoMatching:
    def test_match_shipto_by_postal_city(self):
        result = match_shipto(
            _PARTNERS,
            soldto="15000000",
            name_query="ELM LEBLANC MULHOUSE",
            postal_query="68100",
            city_query="MULHOUSE",
        )
        assert result["shipto"] == "15000010"

    def test_shipto_filtered_by_soldto(self):
        """Ship-to candidates are pre-filtered: no REXEL partner for ELM soldto."""
        with pytest.raises(MatchingError, match="SHIPTO_LOW_CONFIDENCE|SHIPTO_AMBIGUOUS|SHIPTO_NO_CANDIDATES"):
            match_shipto(
                _PARTNERS,
                soldto="17000000",  # PPC has no partners in our list
                name_query="ELM",
                postal_query="67500",
            )

    def test_street_only_rejected(self):
        """Street-only evidence must not qualify per n8n matching policy."""
        # Provide only street evidence, no postal, no city
        with pytest.raises(MatchingError, match="SHIPTO_WEAK_EVIDENCE|SHIPTO_LOW_CONFIDENCE"):
            match_shipto(
                _PARTNERS,
                soldto="15000000",
                name_query="",
                street_query="RUE PASTEUR",
                postal_query="",
                city_query="",
            )

    def test_no_candidates_raises(self):
        with pytest.raises(MatchingError, match="SHIPTO_NO_CANDIDATES"):
            match_shipto(
                _PARTNERS,
                soldto="99999999",
                name_query="nobody",
            )
