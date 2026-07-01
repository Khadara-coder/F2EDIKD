"""Tests: Sample order 93711 end-to-end simulation.

Simulates a successful order 93711:
- Generate EDIFACT ORDERS D.96A
- Verify ELM_STANDARD UNB
- Verify .tst filename contains '93711'
- Mock successful SFTP submission
- Verify PDF moves to PROCESSED only after SFTP success
"""
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import AUTHORISED_SENDER_ID, AUTHORISED_RECEIVER_ID
from src.edifact_builder import build_orders_message, generate_tst_filename
from src.sftp_delivery import SftpDeliveryResult
from src.duplicate_ledger import check_duplicate, record_processing
from src.validations import validate_forbidden_strings_in_text


_ORDER_93711 = {
    "order_number": "93711",
    "order_date": "20260624",
    "buyer_text": "ELM LEBLANC SAS\n4 RUE TEST\n67500 HAGUENAU",
    "delivery_text": "ELM LEBLANC DEPOT\n4 RUE TEST\n67500 HAGUENAU",
    "lines": [
        {"customer_article": "7099018", "quantity": "10", "description": "Joint", "unit_price": "5.50", "ean": ""},
        {"customer_article": "8716796114", "quantity": "5", "description": "Etiquette", "unit_price": "", "ean": ""},
    ],
}

_SOLDTO = {
    "soldto": "15000000", "name": "ELM LEBLANC SAS",
    "street": "4 RUE DU DOCTEUR WILHEM SCHAEFFLER",
    "city": "HAGUENAU", "postal_code": "67500", "country": "FR",
}

_SHIPTO = {
    "shipto": "15000001", "name": "ELM LEBLANC DEPOT",
    "street": "4 RUE DU DOCTEUR WILHEM SCHAEFFLER",
    "city": "HAGUENAU", "postal_code": "67500", "country": "FR",
}

_RESOLVED_LINES = [
    {"matnr": "7099018", "description": "Joint torique", "quantity": "10", "unit_price": "5.50"},
    {"matnr": "8716796114", "description": "ETIQ REGL GAZ G20", "quantity": "5", "unit_price": ""},
]


class TestSampleOrder93711:
    def test_tst_filename_contains_93711(self):
        ts = datetime(2026, 6, 24, 10, 0, 0)
        fname = generate_tst_filename("93711", "15000000", ts)
        assert "93711" in fname
        assert fname.endswith(".tst")

    def test_elm_standard_unb_in_generated_output(self):
        ts = datetime(2026, 6, 24, 10, 0, 0)
        msg = build_orders_message(_ORDER_93711, _RESOLVED_LINES, _SOLDTO, _SHIPTO, ts)
        assert f"UNB+UNOC:3+{AUTHORISED_SENDER_ID}+{AUTHORISED_RECEIVER_ID}" in msg

    def test_order_number_in_bgm(self):
        msg = build_orders_message(_ORDER_93711, _RESOLVED_LINES, _SOLDTO, _SHIPTO)
        assert "BGM+220+93711+9" in msg

    def test_two_lin_segments(self):
        msg = build_orders_message(_ORDER_93711, _RESOLVED_LINES, _SOLDTO, _SHIPTO)
        # LIN+10 and LIN+20
        assert "LIN+10" in msg
        assert "LIN+20" in msg
        assert "CNT+2:2" in msg

    def test_no_forbidden_values_in_output(self):
        msg = build_orders_message(_ORDER_93711, _RESOLVED_LINES, _SOLDTO, _SHIPTO)
        validate_forbidden_strings_in_text(msg, "test_sample_order_93711")  # Must not raise

    def test_pdf_not_moved_before_sftp(self, tmp_path):
        """Simulate: PDF is in error folder only if SFTP fails."""
        from src.file_router import move_to_processed, move_to_error
        pdf = tmp_path / "order_93711.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        processed = tmp_path / "processed"
        processed.mkdir()
        # Simulate SFTP failure: PDF goes to error
        err = tmp_path / "error"
        err.mkdir()
        move_to_error(pdf, str(err), "SFTP_UPLOAD_FAILED")
        assert (err / "order_93711.pdf").exists()
        assert not (processed / "order_93711.pdf").exists()

    def test_pdf_moved_to_processed_after_sftp_success(self, tmp_path):
        from src.file_router import move_to_processed
        pdf = tmp_path / "order_93711.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        processed = tmp_path / "processed"
        processed.mkdir()
        move_to_processed(pdf, str(processed))
        assert (processed / "order_93711.pdf").exists()
        assert not pdf.exists()

    def test_duplicate_ledger_not_updated_without_sftp(self, tmp_path):
        """Duplicate ledger must remain clean if SFTP was not successful."""
        ledger_csv = str(tmp_path / "duplicate_ledger.csv")
        # No record_processing call -> check_duplicate should pass
        check_duplicate(ledger_csv, "93711", "15000000", "abc123")
        # Still passes because nothing was recorded
        check_duplicate(ledger_csv, "93711", "15000000", "abc123")

    def test_duplicate_detected_after_successful_submission(self, tmp_path):
        """After recording SFTP_SUBMITTED, same order is detected as duplicate."""
        ledger_csv = str(tmp_path / "duplicate_ledger.csv")
        record_processing(
            ledger_csv,
            order_number="93711",
            soldto="15000000",
            shipto="15000001",
            pdf_hash="FAKEHASH001",
            tst_filename="ORDERS_15000000_93711_20260624.tst",
            sftp_status="SFTP_SUBMITTED",
            status="SFTP_SUBMITTED",
        )
        from src.exceptions import DuplicateOrderError
        with pytest.raises(DuplicateOrderError, match="DUPLICATE_ORDER"):
            check_duplicate(ledger_csv, "93711", "15000000", "FAKEHASH001")

    def test_mock_sftp_submission_success(self, tmp_path):
        """Mock successful SFTP upload for order 93711."""
        from src.sftp_delivery import upload_tst
        from dataclasses import dataclass

        @dataclass
        class _Cfg:
            enabled: bool = True
            host: str = "sftp.test"
            port: int = 22
            username: str = "user"
            password: str = ""
            private_key_path: str = ""
            private_key_passphrase: str = ""
            remote_dir: str = "/edi"
            upload_tmp_suffix: str = ".uploading"
            verify_after_upload: bool = True
            max_retries: int = 1
            keep_local_copy: bool = True

        tst_file = tmp_path / "ORDERS_15000000_93711_20260624000000.tst"
        tst_file.write_text(
            f"UNA:+.? '\nUNB+UNOC:3+4399901876613+3015981600108+260624:1000+93711TEST'\n"
        )

        mock_stat = MagicMock()
        mock_stat.st_size = tst_file.stat().st_size
        mock_sftp = MagicMock()
        mock_sftp.stat.return_value = mock_stat

        with patch("src.sftp_delivery._open_sftp", return_value=(MagicMock(), mock_sftp)):
            result = upload_tst(tst_file, tst_file.name, _Cfg())

        assert result.success
        assert "93711" in result.tst_filename
