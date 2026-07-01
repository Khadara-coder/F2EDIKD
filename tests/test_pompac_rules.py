"""Tests: POMPAC material resolution rules."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.pompac_rules import resolve_material, LookupTables
from src.exceptions import MaterialResolutionError


def _make_lookups(
    ean_map: dict = None,
    fourretout_map: dict = None,
    discontinued: frozenset = None,
    roh: frozenset = None,
) -> LookupTables:
    return LookupTables(
        ean_to_matnr=ean_map or {},
        fourretout_to_matnr=fourretout_map or {},
        discontinued=discontinued or frozenset(),
        roh_noncommercial=roh or frozenset(),
    )


_MATERIALS = {
    "7099018": "Joint torique",
    "8716796114": "ETIQ REGL GAZ G20",
    "7738113621": "CS38 FR GC9000iW",
}


class TestPompacMaterialResolution:
    def test_ean_lookup(self):
        lookups = _make_lookups(ean_map={"3700000000001": "7099018"})
        result = resolve_material(
            article_code="CUST001",
            description="Joint",
            ean_code="3700000000001",
            materials_master=_MATERIALS,
            lookups=lookups,
        )
        assert result.matnr == "7099018"
        assert result.resolution_method == "EAN"

    def test_ean_lookup_takes_priority_over_fourretout(self):
        lookups = _make_lookups(
            ean_map={"3700000000001": "7099018"},
            fourretout_map={"CUST001": "8716796114"},
        )
        result = resolve_material(
            article_code="CUST001",
            description="Joint",
            ean_code="3700000000001",
            materials_master=_MATERIALS,
            lookups=lookups,
        )
        assert result.matnr == "7099018"
        assert result.resolution_method == "EAN"

    def test_fourretout_correction(self):
        lookups = _make_lookups(fourretout_map={"REF001": "8716796114"})
        result = resolve_material(
            article_code="ref001",  # case insensitive
            description="Etiquette",
            ean_code="",
            materials_master=_MATERIALS,
            lookups=lookups,
        )
        assert result.matnr == "8716796114"
        assert result.resolution_method == "FOURRETOUT"

    def test_direct_match(self):
        lookups = _make_lookups()
        result = resolve_material(
            article_code="7099018",
            description="",
            ean_code="",
            materials_master=_MATERIALS,
            lookups=lookups,
        )
        assert result.matnr == "7099018"
        assert result.resolution_method == "DIRECT"

    def test_fuzzy_description_match(self):
        lookups = _make_lookups()
        result = resolve_material(
            article_code="",
            description="joint torique",
            ean_code="",
            materials_master=_MATERIALS,
            lookups=lookups,
        )
        assert result.matnr == "7099018"
        assert result.resolution_method == "FUZZY"

    def test_unknown_material_rejected(self):
        lookups = _make_lookups()
        with pytest.raises(MaterialResolutionError, match="UNKNOWN_MATERIAL"):
            resolve_material(
                article_code="ZZZNOTEXIST",
                description="Something completely unrelated",
                ean_code="",
                materials_master=_MATERIALS,
                lookups=lookups,
            )

    def test_discontinued_rejection(self):
        lookups = _make_lookups(discontinued=frozenset({"7099018"}))
        with pytest.raises(MaterialResolutionError, match="DISCONTINUED_MATERIAL"):
            resolve_material(
                article_code="7099018",
                description="",
                ean_code="",
                materials_master=_MATERIALS,
                lookups=lookups,
            )

    def test_roh_noncommercial_rejection(self):
        lookups = _make_lookups(roh=frozenset({"8716796114"}))
        with pytest.raises(MaterialResolutionError, match="ROH_NONCOMMERCIAL"):
            resolve_material(
                article_code="8716796114",
                description="",
                ean_code="",
                materials_master=_MATERIALS,
                lookups=lookups,
            )

    def test_dummy_registration_articles(self):
        """1111 and 2222 are registered as dummy POMPAC materials."""
        lookups = _make_lookups(fourretout_map={"1111": "7099018", "2222": "8716796114"})
        r1 = resolve_material(
            article_code="1111", description="", ean_code="",
            materials_master=_MATERIALS, lookups=lookups,
        )
        assert r1.matnr == "7099018"
        r2 = resolve_material(
            article_code="2222", description="", ean_code="",
            materials_master=_MATERIALS, lookups=lookups,
        )
        assert r2.matnr == "8716796114"
