"""Tests: EDIFACT ORDERS D.96A builder."""
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import AUTHORISED_SENDER_ID, AUTHORISED_RECEIVER_ID
from src.edifact_builder import build_orders_message, generate_tst_filename
from src.exceptions import EdifactBuildError, ForbiddenProfileError


def _minimal_order(order_number: str = "TEST001") -> dict:
    return {"order_number": order_number, "order_date": "20260624"}


def _minimal_soldto() -> dict:
    return {
        "soldto": "15000000", "name": "ELM LEBLANC",
        "street": "4 RUE TEST", "city": "HAGUENAU",
        "postal_code": "67500", "country": "FR",
    }


def _minimal_shipto() -> dict:
    return {
        "shipto": "15000001", "name": "DEPOT HAGUENAU",
        "street": "5 RUE TEST", "city": "HAGUENAU",
        "postal_code": "67500", "country": "FR",
    }


def _minimal_lines(n: int = 1) -> list:
    return [
        {
            "matnr": f"7099018",
            "description": f"Test material {i+1}",
            "quantity": str(10 * (i + 1)),
            "unit_price": "12.50",
        }
        for i in range(n)
    ]


class TestEdifactBuilder:
    def test_una_present(self):
        msg = build_orders_message(
            _minimal_order(), _minimal_lines(), _minimal_soldto(), _minimal_shipto()
        )
        assert msg.startswith("UNA:+.? ")

    def test_unb_uses_elm_standard(self):
        msg = build_orders_message(
            _minimal_order(), _minimal_lines(), _minimal_soldto(), _minimal_shipto()
        )
        assert f"UNB+UNOC:3+{AUTHORISED_SENDER_ID}+{AUTHORISED_RECEIVER_ID}" in msg

    def test_unb_exact_prefix(self):
        msg = build_orders_message(
            _minimal_order(), _minimal_lines(), _minimal_soldto(), _minimal_shipto()
        )
        lines = msg.split("'")
        unb_line = next((l.strip() for l in lines if l.strip().startswith("UNB")), None)
        assert unb_line is not None
        assert unb_line.startswith("UNB+UNOC:3+4399901876613+3015981600108+")

    def test_unz_control_ref_matches_unb(self):
        ts = datetime(2026, 6, 24, 10, 30, 0)
        msg = build_orders_message(
            _minimal_order("TEST001"), _minimal_lines(), _minimal_soldto(), _minimal_shipto(),
            generation_ts=ts,
        )
        lines = [l.strip() for l in msg.split("'") if l.strip()]
        unb = next(l for l in lines if l.startswith("UNB+"))
        unz = next(l for l in lines if l.startswith("UNZ+"))
        # Control ref is last element of UNB
        ctrl_ref_unb = unb.split("+")[-1]
        ctrl_ref_unz = unz.split("+")[-1]
        assert ctrl_ref_unb == ctrl_ref_unz, "UNZ control ref must match UNB"

    def test_unt_segment_count_correct(self):
        msg = build_orders_message(
            _minimal_order(), _minimal_lines(2), _minimal_soldto(), _minimal_shipto()
        )
        lines = [l.strip() for l in msg.split("'") if l.strip()]
        unt = next(l for l in lines if l.startswith("UNT+"))
        unt_count = int(unt.split("+")[1])
        # Count all segments between UNH and UNT inclusive
        in_message = False
        count = 0
        for seg in lines:
            if seg.startswith("UNH+"):
                in_message = True
            if in_message:
                count += 1
            if seg.startswith("UNT+"):
                break
        assert unt_count == count, f"UNT count {unt_count} != actual {count}"

    def test_qty21_pce_present(self):
        msg = build_orders_message(
            _minimal_order(), _minimal_lines(), _minimal_soldto(), _minimal_shipto()
        )
        assert "QTY+21:" in msg
        assert ":PCE" in msg

    def test_bgm_220(self):
        msg = build_orders_message(
            _minimal_order(), _minimal_lines(), _minimal_soldto(), _minimal_shipto()
        )
        assert "BGM+220+TEST001+9" in msg

    def test_no_lines_raises(self):
        with pytest.raises(EdifactBuildError):
            build_orders_message(_minimal_order(), [], _minimal_soldto(), _minimal_shipto())

    def test_no_order_number_raises(self):
        with pytest.raises(EdifactBuildError):
            build_orders_message(
                {"order_number": "", "order_date": "20260624"},
                _minimal_lines(), _minimal_soldto(), _minimal_shipto()
            )

    def test_forbidden_sender_not_in_output(self):
        msg = build_orders_message(
            _minimal_order(), _minimal_lines(), _minimal_soldto(), _minimal_shipto()
        )
        assert "3020810000707" not in msg
        assert "54209794400681" not in msg

    def test_tst_filename_contains_order_number(self):
        fname = generate_tst_filename("93711", "15000000")
        assert "93711" in fname
        assert fname.endswith(".tst")

    def test_multi_line_cnt(self):
        msg = build_orders_message(
            _minimal_order(), _minimal_lines(3), _minimal_soldto(), _minimal_shipto()
        )
        assert "CNT+2:3" in msg

    def test_delivery_date_dtm2(self):
        order = {"order_number": "TEST001", "order_date": "20260624", "delivery_date": "20260715"}
        msg = build_orders_message(
            order, _minimal_lines(), _minimal_soldto(), _minimal_shipto()
        )
        assert "DTM+137:20260624:102" in msg
        assert "DTM+2:20260715:102" in msg

    def test_line_unit_from_review(self):
        lines = [{
            "matnr": "7099018",
            "description": "Test",
            "quantity": "5",
            "unit_price": "10.00",
            "unit": "PCE",
        }]
        msg = build_orders_message(
            _minimal_order(), lines, _minimal_soldto(), _minimal_shipto()
        )
        assert "QTY+21:5:PCE" in msg
