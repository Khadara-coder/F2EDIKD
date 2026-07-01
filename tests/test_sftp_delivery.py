"""Tests: SFTP delivery module."""
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.sftp_delivery import upload_tst, SftpDeliveryResult


@dataclass
class _MockSftpConfig:
    enabled: bool = True
    host: str = "sftp.test.local"
    port: int = 22
    username: str = "testuser"
    password: str = "MASKED"
    private_key_path: str = ""
    private_key_passphrase: str = ""
    remote_dir: str = "/remote/edi"
    upload_tmp_suffix: str = ".uploading"
    verify_after_upload: bool = True
    max_retries: int = 2
    keep_local_copy: bool = True


class TestSftpDelivery:
    def test_missing_local_file_returns_failure(self, tmp_path):
        cfg = _MockSftpConfig()
        missing = tmp_path / "does_not_exist.tst"
        result = upload_tst(missing, "test.tst", cfg)
        assert not result.success
        assert "LOCAL_FILE_MISSING" in result.error_reason

    def test_successful_upload(self, tmp_path):
        """Mock SFTP: upload, rename, stat all succeed."""
        tst_file = tmp_path / "ORDERS_15000000_93711.tst"
        tst_file.write_text("UNA:+.? '\nUNB+UNOC:3+4399901876613+3015981600108+260624:1030+REF001'\n",
                            encoding="utf-8")
        cfg = _MockSftpConfig()

        mock_stat = MagicMock()
        mock_stat.st_size = tst_file.stat().st_size
        mock_sftp = MagicMock()
        mock_sftp.stat.return_value = mock_stat

        mock_transport = MagicMock()
        mock_sftp_class = MagicMock(return_value=mock_sftp)

        with patch("src.sftp_delivery._open_sftp", return_value=(mock_transport, mock_sftp)):
            result = upload_tst(tst_file, "ORDERS_15000000_93711.tst", cfg)

        assert result.success
        assert result.tst_filename == "ORDERS_15000000_93711.tst"
        assert "/remote/edi/ORDERS_15000000_93711.tst" in result.remote_path
        # Verify rename was called
        mock_sftp.rename.assert_called_once()
        # Verify stat was called for verification
        mock_sftp.stat.assert_called_once()

    def test_sftp_upload_failure_returns_error_result(self, tmp_path):
        """Mock SFTP connection failure -> returns SftpDeliveryResult(success=False)."""
        tst_file = tmp_path / "test.tst"
        tst_file.write_text("EDIFACT", encoding="utf-8")
        cfg = _MockSftpConfig(max_retries=1)

        from src.exceptions import SftpDeliveryError
        with patch("src.sftp_delivery._open_sftp", side_effect=SftpDeliveryError("Connection refused")):
            result = upload_tst(tst_file, "test.tst", cfg)

        assert not result.success
        assert "SFTP_UPLOAD_FAILED" in result.error_reason

    def test_verify_failure_returns_error(self, tmp_path):
        """If stat fails after rename, return failure."""
        tst_file = tmp_path / "test.tst"
        tst_file.write_text("EDIFACT", encoding="utf-8")
        cfg = _MockSftpConfig(max_retries=1)

        mock_sftp = MagicMock()
        mock_sftp.stat.side_effect = IOError("File not found on remote")
        mock_transport = MagicMock()

        with patch("src.sftp_delivery._open_sftp", return_value=(mock_transport, mock_sftp)):
            result = upload_tst(tst_file, "test.tst", cfg)

        assert not result.success

    def test_no_password_in_logs(self, tmp_path, caplog):
        """Sensitive values are never logged."""
        tst_file = tmp_path / "test.tst"
        tst_file.write_text("EDIFACT", encoding="utf-8")
        cfg = _MockSftpConfig(password="SUPER_SECRET_PASSWORD")

        with patch("src.sftp_delivery._open_sftp", side_effect=Exception("fail")):
            upload_tst(tst_file, "test.tst", cfg)

        assert "SUPER_SECRET_PASSWORD" not in caplog.text
