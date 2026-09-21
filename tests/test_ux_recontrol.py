import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ux_recontrol import can_close_after_recontrol


def review(**overrides):
    value = {
        "order": {"customerOrderNumber": "", "orderDate": None, "requestedDeliveryDate": None},
        "partners": [
            {"partnerFunction": "soldto", "partnerCode": ""},
            {"partnerFunction": "shipto", "partnerCode": ""},
        ],
        "lines": [],
    }
    value.update(overrides)
    return value


def test_header_and_partner_rechecks_use_current_values():
    current = review(
        order={"customerOrderNumber": "PO-42", "orderDate": "2026-09-21", "requestedDeliveryDate": "2026-10-01"},
        partners=[
            {"partnerFunction": "soldto", "partnerCode": "1000"},
            {"partnerFunction": "shipto", "partnerCode": "2000"},
        ],
    )
    assert can_close_after_recontrol("ORDER_KEY_MISSING", current)
    assert can_close_after_recontrol("ORDER_DATE_INVALID", current)
    assert can_close_after_recontrol("SOLDTO_NOT_FOUND", current)
    assert can_close_after_recontrol("SHIPTO_NO_STRONG_MATCH", current)


def test_recheck_does_not_close_technical_or_edi_issue_by_click():
    current = review(order={"customerOrderNumber": "PO-42"})
    assert not can_close_after_recontrol("EDIFACT_MISSING_BGM", current)
    assert not can_close_after_recontrol("MASTERDATA_MISSING", current)


def test_line_rechecks_require_valid_current_lines():
    assert not can_close_after_recontrol("NO_LINE_ITEMS", review())
    current = review(lines=[{"boschArticle": "A-1", "quantity": 2}])
    assert can_close_after_recontrol("NO_LINE_ITEMS", current)
    assert can_close_after_recontrol("ARTICLE_QUANTITY_INVALID", current)
    assert can_close_after_recontrol("ARTICLE_NOT_FOUND", current)