"""SFTP delivery module for EDIFACT Orders Generator.

Upload strategy:
1. Upload local .tst to remote as <filename>.uploading
2. Rename remote temp file to <filename>
3. Verify remote file exists via stat
4. Mark delivery status as SFTP_SUBMITTED

Never prints password or private key content in logs.
All sensitive values are masked in diagnostics.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .exceptions import SftpDeliveryError

log = logging.getLogger("edifact.sftp")

_MASK = "***MASKED***"


# --------------------------------------------------------------------------- #
# Result type
# --------------------------------------------------------------------------- #

@dataclass
class SftpDeliveryResult:
    """Outcome of an SFTP upload attempt."""
    success: bool
    tst_filename: str
    remote_path: str = ""
    file_size: int = 0
    error_reason: str = ""
    attempts: int = 0


# --------------------------------------------------------------------------- #
# SFTP client helper
# --------------------------------------------------------------------------- #

def _open_sftp(sftp_cfg: object) -> tuple[object, object]:
    """Open a Paramiko SFTP connection.

    Prefers private-key authentication; falls back to password if no key is provided.
    Never logs credentials.

    Returns:
        (transport, sftp_client) tuple.
    """
    try:
        import paramiko  # type: ignore
    except ImportError as exc:
        raise SftpDeliveryError(
            "paramiko is not installed. Add 'paramiko' to requirements.txt."
        ) from exc

    host: str = sftp_cfg.host  # type: ignore
    port: int = sftp_cfg.port  # type: ignore
    username: str = sftp_cfg.username  # type: ignore
    password: str = sftp_cfg.password  # type: ignore
    pk_path: str = sftp_cfg.private_key_path  # type: ignore
    pk_passphrase: str = sftp_cfg.private_key_passphrase  # type: ignore

    log.debug("Opening SFTP connection: host=%s port=%d user=%s", host, port, username)

    transport = paramiko.Transport((host, port))

    try:
        if pk_path:
            log.debug("SFTP auth: private key (path=%s)", pk_path)
            try:
                pkey = paramiko.RSAKey.from_private_key_file(
                    pk_path,
                    password=pk_passphrase if pk_passphrase else None,
                )
            except Exception:
                # Try Ed25519
                try:
                    pkey = paramiko.Ed25519Key.from_private_key_file(
                        pk_path,
                        password=pk_passphrase if pk_passphrase else None,
                    )
                except Exception as exc2:
                    raise SftpDeliveryError(
                        f"SFTP private key load failed: {type(exc2).__name__}. "
                        f"Path: {pk_path}"
                    ) from exc2
            transport.connect(username=username, pkey=pkey)
        else:
            log.debug("SFTP auth: password (masked)")
            transport.connect(username=username, password=password)

        sftp = paramiko.SFTPClient.from_transport(transport)
        return transport, sftp
    except SftpDeliveryError:
        raise
    except Exception as exc:
        transport.close()
        raise SftpDeliveryError(
            f"SFTP connection failed: {type(exc).__name__}: {exc}. "
            f"host={host} port={port} user={username} "
            f"auth={'key' if pk_path else 'password'}"
        ) from exc


def _close_sftp(transport: object, sftp: object) -> None:
    """Safely close SFTP client and transport."""
    try:
        if sftp is not None:
            sftp.close()  # type: ignore
    except Exception:
        pass
    try:
        if transport is not None:
            transport.close()  # type: ignore
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Upload logic
# --------------------------------------------------------------------------- #

def upload_tst(
    local_path: Path,
    tst_filename: str,
    sftp_cfg: object,
) -> SftpDeliveryResult:
    """Upload a .tst file to the configured SFTP remote folder.

    Strategy:
    1. Upload as <filename>.uploading
    2. Rename remote temp to <filename>
    3. Verify remote file exists via stat
    4. Return SftpDeliveryResult(success=True) on success

    Args:
        local_path: Path to the local .tst file.
        tst_filename: Final remote filename (without path).
        sftp_cfg: SftpConfig dataclass instance.

    Returns:
        SftpDeliveryResult.
    """
    max_retries: int = getattr(sftp_cfg, "max_retries", 3)  # type: ignore
    remote_dir: str = getattr(sftp_cfg, "remote_dir", "")  # type: ignore
    tmp_suffix: str = getattr(sftp_cfg, "upload_tmp_suffix", ".uploading")  # type: ignore
    verify: bool = getattr(sftp_cfg, "verify_after_upload", True)  # type: ignore

    if not local_path.exists():
        return SftpDeliveryResult(
            success=False,
            tst_filename=tst_filename,
            error_reason=f"LOCAL_FILE_MISSING: {local_path}",
        )

    file_size = local_path.stat().st_size
    remote_final = f"{remote_dir.rstrip('/')}/{tst_filename}"
    remote_tmp = f"{remote_final}{tmp_suffix}"

    last_error = ""
    for attempt in range(1, max_retries + 1):
        transport = None
        sftp = None
        try:
            log.info(
                "SFTP upload attempt %d/%d: local=%s remote=%s",
                attempt, max_retries, local_path.name, remote_final,
            )
            transport, sftp = _open_sftp(sftp_cfg)

            # Step 1: Upload to temp name
            sftp.put(str(local_path), remote_tmp)  # type: ignore
            log.debug("SFTP put complete: temp=%s", remote_tmp)

            # Step 2: Atomic rename
            sftp.rename(remote_tmp, remote_final)  # type: ignore
            log.debug("SFTP rename complete: %s -> %s", remote_tmp, remote_final)

            # Step 3: Verify
            if verify:
                try:
                    stat_result = sftp.stat(remote_final)  # type: ignore
                    log.info(
                        "SFTP verification OK: %s size=%s",
                        remote_final, stat_result.st_size,
                    )
                except Exception as exc:
                    raise SftpDeliveryError(
                        f"SFTP_VERIFY_FAILED: Remote file not found after rename: "
                        f"{remote_final}: {exc}"
                    ) from exc

            return SftpDeliveryResult(
                success=True,
                tst_filename=tst_filename,
                remote_path=remote_final,
                file_size=file_size,
                attempts=attempt,
            )

        except SftpDeliveryError as exc:
            last_error = str(exc)
            log.warning("SFTP attempt %d/%d failed: %s", attempt, max_retries, last_error)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            log.warning("SFTP attempt %d/%d error: %s", attempt, max_retries, last_error)
        finally:
            _close_sftp(transport, sftp)

        # Clean up remote temp if possible
        if attempt < max_retries:
            time.sleep(2 ** attempt)  # exponential backoff

    return SftpDeliveryResult(
        success=False,
        tst_filename=tst_filename,
        remote_path=remote_final,
        file_size=file_size,
        error_reason=f"SFTP_UPLOAD_FAILED after {max_retries} attempts: {last_error}",
        attempts=max_retries,
    )
