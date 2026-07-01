"""Tests: Forbidden UNB strings must not appear in generated output or active code."""
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import FORBIDDEN_SENDER_IDS, FORBIDDEN_RECEIVER_IDS
from src.edifact_builder import build_orders_message
from src.validations import validate_forbidden_strings_in_text
from src.exceptions import ForbiddenProfileError

_FORBIDDEN = ["3020810000707", "54209794400681"]
_PROJECT_SRC = Path(__file__).parent.parent / "src"
_LOOKUPS_DIR = Path(__file__).parent.parent / "lookups"
_CONFIG_FILE = Path(__file__).parent.parent / "config.ini"


class TestForbiddenStrings:
    def test_forbidden_ids_in_module(self):
        """FORBIDDEN_SENDER_IDS must contain both forbidden values."""
        for fv in _FORBIDDEN:
            assert fv in FORBIDDEN_SENDER_IDS or fv in FORBIDDEN_RECEIVER_IDS

    def test_validate_function_raises_on_forbidden(self):
        for fv in _FORBIDDEN:
            with pytest.raises(ForbiddenProfileError):
                validate_forbidden_strings_in_text(f"UNB+UNOC:3+{fv}+3015981600108", "test")

    def test_generated_edifact_does_not_contain_forbidden(self):
        """Generated ORDERS message must not contain forbidden values."""
        order = {"order_number": "TEST001", "order_date": "20260624"}
        soldto = {
            "soldto": "15000000", "name": "TEST", "street": "ST",
            "city": "CITY", "postal_code": "67500", "country": "FR",
        }
        shipto = {
            "shipto": "15000001", "name": "DEPOT", "street": "ST",
            "city": "CITY", "postal_code": "67500", "country": "FR",
        }
        lines = [{"matnr": "7099018", "description": "Joint", "quantity": "5", "unit_price": ""}]
        msg = build_orders_message(order, lines, soldto, shipto)
        for fv in _FORBIDDEN:
            assert fv not in msg, f"Forbidden value {fv!r} found in EDIFACT output!"

    def test_src_files_do_not_activate_forbidden_values(self):
        """Source code files must not have forbidden values outside the forbidden-list guard."""
        if not _PROJECT_SRC.exists():
            pytest.skip("src/ directory not found")
        issues = []
        for py_file in _PROJECT_SRC.glob("*.py"):
            text = py_file.read_text(encoding="utf-8-sig", errors="ignore")
            for fv in _FORBIDDEN:
                if fv in text:
                    lines_with_fv = [l.strip() for l in text.split("\n") if fv in l]
                    for ctx in lines_with_fv:
                        # Allow only in the forbidden-list constant definitions or test assertions
                        if not any(
                            guard in ctx
                            for guard in [
                                "FORBIDDEN", "frozenset", "forbidden", "_FORBIDDEN",
                                "assert", "#",
                            ]
                        ):
                            issues.append(f"{py_file.name}: {ctx[:80]}")
        assert not issues, f"Forbidden values found in active code paths:\n" + "\n".join(issues)

    def test_unb_profiles_csv_has_no_forbidden(self):
        """lookups/unb_profiles.csv must not contain forbidden values."""
        if not _LOOKUPS_DIR.exists():
            pytest.skip("lookups/ dir not found")
        csv_path = _LOOKUPS_DIR / "unb_profiles.csv"
        if not csv_path.exists():
            pytest.skip("unb_profiles.csv not found")
        content = csv_path.read_text(encoding="utf-8-sig")
        for fv in _FORBIDDEN:
            assert fv not in content, f"Forbidden value {fv!r} in unb_profiles.csv"

    def test_config_ini_has_no_forbidden(self):
        """config.ini must not contain forbidden values."""
        if not _CONFIG_FILE.exists():
            pytest.skip("config.ini not found")
        content = _CONFIG_FILE.read_text(encoding="utf-8")
        for fv in _FORBIDDEN:
            assert fv not in content, f"Forbidden value {fv!r} in config.ini"
