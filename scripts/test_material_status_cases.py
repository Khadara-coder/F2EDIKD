#!/usr/bin/env python3
"""Smoke test Materials Statut rules against runtime masterdata.

Usage (from repo root):
  python scripts/test_material_status_cases.py
  python scripts/test_material_status_cases.py --matnr 87183105320
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Real MATNRs from 10564_Materials.parquet (sync GHE) — use for revue commande manual tests.
CASES = [
    ("7739833464", "Article disponible - aucune anomalie"),
    ("87183105320", "no sale (VMSTA 92) - warning arrete"),
    ("7739834567", "remplacement (chaine Statut MATNR)"),
    ("87072062820", "remplacement puis no sale (chaine)"),
    ("99999999999", "absent masterdata - erreur"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Materials Statut resolution")
    parser.add_argument("--matnr", help="Single MATNR to evaluate")
    parser.add_argument(
        "--runtime-dir",
        default=str(ROOT / "data" / "masterdata"),
        help="Masterdata runtime directory",
    )
    args = parser.parse_args()

    from src.masterdata_runtime import configure, load_cache, material_line_status

    runtime = Path(args.runtime_dir)
    configure(runtime_dir=str(runtime))
    load_cache()

    targets = [(args.matnr, "custom")] if args.matnr else [(m, label) for m, label in CASES]

    print(f"Runtime: {runtime}")
    print("-" * 72)
    for matnr, label in targets:
        status = material_line_status(matnr)
        kind = status.get("kind")
        repl = status.get("replacement")
        chain = status.get("replacement_chain")
        print(f"MATNR {matnr} — {label}")
        print(f"  kind={kind}  statut={status.get('statut')!r}  replacement={repl!r}")
        if chain:
            print(f"  chain={' -> '.join(chain)}")
        if status.get("replacement_cycle"):
            print("  cycle=True")
        if status.get("via_replacement"):
            print("  via_replacement=True")
        if status.get("replacement_missing"):
            print("  replacement_missing=True")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
