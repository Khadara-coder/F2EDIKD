#!/usr/bin/env python3
"""FastAPI entrypoint for EDIFACT Standalone Orchestrator.

Usage:
    python run_api.py
    uvicorn src.api:app --host 0.0.0.0 --port 8088
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a script
sys.path.insert(0, str(Path(__file__).parent))

from src.api import app  # noqa: E402 (after sys.path)
from src.config_loader import load_config  # noqa: E402

if __name__ == "__main__":
    try:
        import uvicorn  # type: ignore
    except ImportError:
        print("ERROR: uvicorn is not installed. Run: pip install uvicorn[standard]", file=sys.stderr)
        sys.exit(1)

    cfg = load_config()
    logging.basicConfig(
        level=getattr(logging, cfg.logging.level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8088"))

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=cfg.logging.level.lower(),
    )
