"""Logging configuration for EDIFACT Orders Generator."""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path


def setup_logging(
    level: str = "INFO",
    log_file: str = "logs/edifact.log",
    max_bytes: int = 5_242_880,
    backup_count: int = 10,
) -> logging.Logger:
    """Configure root logger with rotating file handler and console handler.

    Args:
        level: Logging level string (DEBUG, INFO, WARNING, ERROR).
        log_file: Path to the rotating log file.
        max_bytes: Maximum log file size before rotation.
        backup_count: Number of backup log files to retain.

    Returns:
        Configured root logger.
    """
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.handlers.clear()

    # Rotating file handler
    fh = logging.handlers.RotatingFileHandler(
        str(log_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    fh.setLevel(numeric_level)
    fh.setFormatter(formatter)
    root.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(numeric_level)
    ch.setFormatter(formatter)
    root.addHandler(ch)

    return root


def get_logger(name: str) -> logging.Logger:
    """Return a named child logger."""
    return logging.getLogger(name)
