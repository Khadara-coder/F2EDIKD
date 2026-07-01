"""Tests: UNB profile enforcement."""
import csv
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import AUTHORISED_PROFILE_ID, AUTHORISED_SENDER_ID, AUTHORISED_RECEIVER_ID, FORBIDDEN_SENDER_IDS
from src.exceptions import ForbiddenProfileError, ConfigError
from src.validations import validate_unb_profile_csv


def _write_profiles_csv(rows: list[dict], tmp_path: Path) -> str:
    p = tmp_path / "unb_profiles.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["profile_id", "charset", "sender_id", "receiver_id"])
        writer.writeheader()
        writer.writerows(rows)
    return str(p)


class TestUnbProfileCsv:
    def test_valid_elm_standard(self, tmp_path):
        """Single ELM_STANDARD row passes validation."""
        csv_path = _write_profiles_csv([
            {"profile_id": "ELM_STANDARD", "charset": "UNOC:3",
             "sender_id": "4399901876613", "receiver_id": "3015981600108"},
        ], tmp_path)
        # Should not raise
        validate_unb_profile_csv(csv_path)

    def test_two_profile_rows_fails(self, tmp_path):
        """Two rows must fail startup."""
        csv_path = _write_profiles_csv([
            {"profile_id": "ELM_STANDARD", "charset": "UNOC:3",
             "sender_id": "4399901876613", "receiver_id": "3015981600108"},
            {"profile_id": "OTHER", "charset": "UNOC:3",
             "sender_id": "9999999999999", "receiver_id": "3015981600108"},
        ], tmp_path)
        with pytest.raises(ForbiddenProfileError, match="exactly 1"):
            validate_unb_profile_csv(csv_path)

    def test_wrong_sender_id_fails(self, tmp_path):
        csv_path = _write_profiles_csv([
            {"profile_id": "ELM_STANDARD", "charset": "UNOC:3",
             "sender_id": "0000000000000", "receiver_id": "3015981600108"},
        ], tmp_path)
        with pytest.raises(ForbiddenProfileError, match="4399901876613"):
            validate_unb_profile_csv(csv_path)

    def test_wrong_receiver_id_fails(self, tmp_path):
        csv_path = _write_profiles_csv([
            {"profile_id": "ELM_STANDARD", "charset": "UNOC:3",
             "sender_id": "4399901876613", "receiver_id": "0000000000000"},
        ], tmp_path)
        with pytest.raises(ForbiddenProfileError, match="3015981600108"):
            validate_unb_profile_csv(csv_path)

    def test_forbidden_sender_id_rejected(self, tmp_path):
        """Known forbidden sender ID 3020810000707 must fail."""
        csv_path = _write_profiles_csv([
            {"profile_id": "ELM_STANDARD", "charset": "UNOC:3",
             "sender_id": "3020810000707", "receiver_id": "3015981600108"},
        ], tmp_path)
        with pytest.raises(ForbiddenProfileError):
            validate_unb_profile_csv(csv_path)

    def test_forbidden_receiver_id_rejected(self, tmp_path):
        """Known forbidden receiver ID 54209794400681 must fail."""
        csv_path = _write_profiles_csv([
            {"profile_id": "ELM_STANDARD", "charset": "UNOC:3",
             "sender_id": "4399901876613", "receiver_id": "54209794400681"},
        ], tmp_path)
        with pytest.raises(ForbiddenProfileError):
            validate_unb_profile_csv(csv_path)

    def test_missing_file_raises_config_error(self, tmp_path):
        with pytest.raises(ConfigError):
            validate_unb_profile_csv(str(tmp_path / "missing.csv"))

    def test_authorised_constants(self):
        assert AUTHORISED_PROFILE_ID == "ELM_STANDARD"
        assert AUTHORISED_SENDER_ID == "4399901876613"
        assert AUTHORISED_RECEIVER_ID == "3015981600108"

    def test_forbidden_set_does_not_contain_authorised(self):
        assert AUTHORISED_SENDER_ID not in FORBIDDEN_SENDER_IDS
        assert AUTHORISED_RECEIVER_ID not in FORBIDDEN_SENDER_IDS
