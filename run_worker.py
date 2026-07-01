#!/usr/bin/env python3
"""Worker process entrypoint for EDIFACT Standalone Orchestrator.

Polls SQLite for queued jobs and processes them via the engine pipeline.

Usage:
    python run_worker.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a script
sys.path.insert(0, str(Path(__file__).parent))

from src.worker import run_forever  # noqa: E402

if __name__ == "__main__":
    run_forever()
