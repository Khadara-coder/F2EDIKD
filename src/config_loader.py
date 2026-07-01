"""Configuration loader for EDIFACT Orders Generator.

Loads config.ini, resolves ${ENV_VAR} placeholders from environment,
and validates required sections/keys.
"""
from __future__ import annotations

import configparser
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import AUTHORISED_PROFILE_ID, AUTHORISED_SENDER_ID, AUTHORISED_RECEIVER_ID
from .exceptions import ConfigError

log = logging.getLogger("edifact.config")

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _resolve_env(value: str) -> str:
    """Replace ${VAR_NAME} tokens with environment variable values."""
    def _replace(m: re.Match) -> str:
        var = m.group(1)
        resolved = os.environ.get(var, "")
        return resolved
    return _ENV_PATTERN.sub(_replace, value)


@dataclass
class PathsConfig:
    pdf_inbox: str
    pdf_processed: str
    pdf_error: str
    local_generated_outbox: str
    sftp_submitted_archive: str
    sftp_failed_archive: str


@dataclass
class N8nConfig:
    analyse_existing_project: bool
    n8n_project_root: str
    analysis_report: str


@dataclass
class MasterDataConfig:
    source_mode: str
    masterdata_root: str
    customers_csv: str
    partners_csv: str
    materials_csv: str
    salesorder_csv: str
    allow_fallback: bool


@dataclass
class EdiConfig:
    unb_profile: str
    syntax_identifier: str
    syntax_version: str
    sender_id: str
    receiver_id: str
    message_type: str
    directory: str
    version: str
    agency: str


@dataclass
class SftpConfig:
    enabled: bool
    host: str
    port: int
    username: str
    password: str
    private_key_path: str
    private_key_passphrase: str
    remote_dir: str
    upload_tmp_suffix: str
    verify_after_upload: bool
    max_retries: int
    keep_local_copy: bool


@dataclass
class RunConfig:
    sleep_minutes: int
    dry_run: bool


@dataclass
class LoggingConfig:
    level: str
    max_bytes: int
    backup_count: int


@dataclass
class DuplicatesConfig:
    enabled: bool
    ledger_csv: str


@dataclass
class AppConfig:
    paths: PathsConfig
    n8n: N8nConfig
    masterdata: MasterDataConfig
    edi: EdiConfig
    sftp: SftpConfig
    run: RunConfig
    logging: LoggingConfig
    duplicates: DuplicatesConfig
    config_path: str = ""


def load_config(config_path: str = "config.ini") -> AppConfig:
    """Load, resolve, and validate the application configuration.

    Args:
        config_path: Path to config.ini.

    Returns:
        Populated AppConfig dataclass.

    Raises:
        ConfigError: If the configuration is invalid or mandatory keys are missing.
    """
    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")

    parser = configparser.RawConfigParser()
    parser.read(str(path), encoding="utf-8")

    def get(section: str, key: str, fallback: str = "") -> str:
        raw = parser.get(section, key, fallback=fallback)
        return _resolve_env(raw).strip()

    def getbool(section: str, key: str, fallback: bool = False) -> bool:
        raw = get(section, key, fallback="true" if fallback else "false")
        return raw.lower() in {"true", "1", "yes", "y"}

    def getint(section: str, key: str, fallback: int = 0) -> int:
        try:
            return int(get(section, key, fallback=str(fallback)))
        except ValueError as exc:
            raise ConfigError(f"[{section}] {key} must be an integer") from exc

    # --- paths ---
    paths = PathsConfig(
        pdf_inbox=get("paths", "pdf_inbox"),
        pdf_processed=get("paths", "pdf_processed"),
        pdf_error=get("paths", "pdf_error"),
        local_generated_outbox=get("paths", "local_generated_outbox", "outbox/local_generated"),
        sftp_submitted_archive=get("paths", "sftp_submitted_archive", "outbox/sftp_submitted"),
        sftp_failed_archive=get("paths", "sftp_failed_archive", "outbox/sftp_failed"),
    )

    # --- n8n ---
    n8n = N8nConfig(
        analyse_existing_project=getbool("n8n", "analyse_existing_project", True),
        n8n_project_root=get("n8n", "n8n_project_root"),
        analysis_report=get("n8n", "analysis_report", "docs/N8N_ANALYSIS_REPORT.md"),
    )

    # --- masterdata ---
    masterdata = MasterDataConfig(
        source_mode=get("masterdata", "source_mode", "databricks_workspace"),
        masterdata_root=get("masterdata", "masterdata_root"),
        customers_csv=get("masterdata", "customers_csv"),
        partners_csv=get("masterdata", "partners_csv"),
        materials_csv=get("masterdata", "materials_csv"),
        salesorder_csv=get("masterdata", "salesorder_csv"),
        allow_fallback=getbool("masterdata", "allow_fallback", False),
    )

    # --- edi ---
    edi = EdiConfig(
        unb_profile=get("edi", "unb_profile", AUTHORISED_PROFILE_ID),
        syntax_identifier=get("edi", "syntax_identifier", "UNOC"),
        syntax_version=get("edi", "syntax_version", "3"),
        sender_id=get("edi", "sender_id", AUTHORISED_SENDER_ID),
        receiver_id=get("edi", "receiver_id", AUTHORISED_RECEIVER_ID),
        message_type=get("edi", "message_type", "ORDERS"),
        directory=get("edi", "directory", "D"),
        version=get("edi", "version", "96A"),
        agency=get("edi", "agency", "UN"),
    )

    # --- sftp ---
    password_env = get("sftp", "password_env", "SFTP_PASSWORD")
    pk_passphrase_env = get("sftp", "private_key_passphrase_env", "SFTP_PRIVATE_KEY_PASSPHRASE")
    sftp = SftpConfig(
        enabled=getbool("sftp", "enabled", False),
        host=get("sftp", "host"),
        port=getint("sftp", "port", 22),
        username=get("sftp", "username"),
        password=os.environ.get(password_env, ""),
        private_key_path=get("sftp", "private_key_path"),
        private_key_passphrase=os.environ.get(pk_passphrase_env, ""),
        remote_dir=get("sftp", "remote_dir"),
        upload_tmp_suffix=get("sftp", "upload_tmp_suffix", ".uploading"),
        verify_after_upload=getbool("sftp", "verify_after_upload", True),
        max_retries=getint("sftp", "max_retries", 3),
        keep_local_copy=getbool("sftp", "keep_local_copy", True),
    )

    # --- run ---
    run = RunConfig(
        sleep_minutes=getint("run", "sleep_minutes", 0),
        dry_run=getbool("run", "dry_run", False),
    )

    # --- logging ---
    logging_cfg = LoggingConfig(
        level=get("logging", "level", "INFO"),
        max_bytes=getint("logging", "max_bytes", 5_242_880),
        backup_count=getint("logging", "backup_count", 10),
    )

    # --- duplicates ---
    duplicates = DuplicatesConfig(
        enabled=getbool("duplicates", "enabled", True),
        ledger_csv=get("duplicates", "ledger_csv", "data/duplicate_ledger.csv"),
    )

    cfg = AppConfig(
        paths=paths,
        n8n=n8n,
        masterdata=masterdata,
        edi=edi,
        sftp=sftp,
        run=run,
        logging=logging_cfg,
        duplicates=duplicates,
        config_path=str(path),
    )

    _validate_edi_profile(cfg)
    log.info("Configuration loaded from: %s", config_path)
    return cfg


def _validate_edi_profile(cfg: AppConfig) -> None:
    """Enforce ELM_STANDARD-only UNB profile and forbidden value checks."""
    from . import FORBIDDEN_SENDER_IDS, FORBIDDEN_RECEIVER_IDS
    from .exceptions import ForbiddenProfileError

    if cfg.edi.unb_profile != AUTHORISED_PROFILE_ID:
        raise ForbiddenProfileError(
            f"UNB profile must be {AUTHORISED_PROFILE_ID!r}. "
            f"Got: {cfg.edi.unb_profile!r}. No alternate profile is permitted."
        )
    if cfg.edi.sender_id != AUTHORISED_SENDER_ID:
        raise ForbiddenProfileError(
            f"EDI sender_id must be {AUTHORISED_SENDER_ID!r}. Got: {cfg.edi.sender_id!r}."
        )
    if cfg.edi.receiver_id != AUTHORISED_RECEIVER_ID:
        raise ForbiddenProfileError(
            f"EDI receiver_id must be {AUTHORISED_RECEIVER_ID!r}. Got: {cfg.edi.receiver_id!r}."
        )
    if cfg.edi.sender_id in FORBIDDEN_SENDER_IDS:
        raise ForbiddenProfileError(
            f"Forbidden sender_id detected: {cfg.edi.sender_id!r}"
        )
    if cfg.edi.receiver_id in FORBIDDEN_RECEIVER_IDS:
        raise ForbiddenProfileError(
            f"Forbidden receiver_id detected: {cfg.edi.receiver_id!r}"
        )
    log.info(
        "UNB profile validated: %s sender=%s receiver=%s",
        cfg.edi.unb_profile, cfg.edi.sender_id, cfg.edi.receiver_id,
    )
