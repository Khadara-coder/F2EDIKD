#!/usr/bin/env python3
"""Run the real File2EDI pipeline over every PDF in the RAG corpus."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "RAG Purchase Orders",
        help="Directory containing command PDFs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "rag_purchase_orders_validation.jsonl",
    )
    args = parser.parse_args()

    import server

    try:
        from tqdm import tqdm
    except ImportError:
        def tqdm(iterable, **_kwargs):
            return iterable

    files = sorted(
        path for path in args.input.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    )
    if not files:
        print(f"Aucun PDF trouvé dans {args.input}")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    counts = Counter()
    errors = 0

    with args.output.open("w", encoding="utf-8") as report:
        progress = tqdm(files, total=len(files), desc="File2EDI", unit="PDF")
        for index, path in enumerate(progress, start=1):
            item_started = time.perf_counter()
            try:
                result = server._local_process_and_respond(
                    path.read_bytes(),
                    path.name,
                    actor="batch-rag-test",
                    bypass_cache=True,
                )
                rejection = result.get("rejection") or {}
                record = {
                    "file": path.name,
                    "status": result.get("status"),
                    "decision": rejection.get("decision"),
                    "reason": rejection.get("reason"),
                    "lines": (result.get("lines") or {}).get("count", 0),
                    "edifact_generated": (result.get("edifact") or {}).get("generated", False),
                    "elapsed_s": round(time.perf_counter() - item_started, 2),
                }
                counts[record["status"] or "UNKNOWN"] += 1
                counts[f"decision:{record['decision'] or 'NONE'}"] += 1
            except Exception as exc:  # keep the batch running after one bad PDF
                errors += 1
                record = {
                    "file": path.name,
                    "status": "EXCEPTION",
                    "error": f"{type(exc).__name__}: {exc}",
                    "elapsed_s": round(time.perf_counter() - item_started, 2),
                }
                counts["EXCEPTION"] += 1

            report.write(json.dumps(record, ensure_ascii=False) + "\n")
            report.flush()
            progress.set_postfix(
                ok=counts.get("OK", 0),
                errors=errors,
                last=record.get("reason") or record.get("status"),
            )

    elapsed = time.perf_counter() - started
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": str(args.input),
        "total_pdfs": len(files),
        "exceptions": errors,
        "elapsed_s": round(elapsed, 2),
        "counts": dict(counts),
        "report": str(args.output),
    }
    summary_path = args.output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())