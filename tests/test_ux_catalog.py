import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ux_catalog import UX_BY_ID, UX_RULES, ux_rule


def test_reference_contains_active_and_future_ux_rules():
    assert len(UX_RULES) == 20
    assert sum(rule["status"] == "active" for rule in UX_RULES) == 18
    assert UX_BY_ID["UX-19"]["status"] == "draft"
    assert UX_BY_ID["UX-20"]["status"] == "draft"


def test_active_anomaly_codes_map_to_business_ux():
    assert ux_rule("ORDER_KEY_MISSING")["ux_id"] == "UX-03"
    assert ux_rule("SHIPTO_NO_STRONG_MATCH")["ux_id"] == "UX-06"
    assert ux_rule("SOLDTO_NOT_FOUND")["ux_id"] == "UX-07"
    assert ux_rule("MATERIAL_STATUS_INVALID")["ux_id"] == "UX-08"
    assert ux_rule("DELIVERY_SFTP_FAILED")["ux_id"] == "UX-18"


def test_recontrol_and_finalization_are_explicit():
    for rule in UX_RULES:
        if rule["status"] == "active" and rule["ux_id"] not in {"UX-02", "UX-12"}:
            assert rule["requires_recontrol"] is True
            assert rule["finalization_required"] is True


def test_future_price_and_freight_ux_have_no_active_codes():
    assert UX_BY_ID["UX-19"]["codes"] == ()
    assert UX_BY_ID["UX-20"]["codes"] == ()