from app.street_types import expand_street_type_abbreviations, normalize_street_for_match


def test_expand_street_type_abbreviations():
    assert "avenue" in expand_street_type_abbreviations("205, Av. General Pruneau")
    assert "boulevard" in expand_street_type_abbreviations("10 bd Haussmann")
    assert "route" in expand_street_type_abbreviations("12 rte de Paris")


def test_normalize_street_for_match_expands_before_compare():
    assert "AVENUE" in normalize_street_for_match("205 Av General Pruneau")
    assert normalize_street_for_match("10 bd Haussmann") == normalize_street_for_match("10 BOULEVARD HAUSSMANN")
